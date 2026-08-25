01 — Architecture: How the Pieces Actually Fit Together
===========================================================

:doc:`../architecture` already has the target component diagram. This page answers a different
question: walking one real request end to end through the actual code, what architectural patterns
are genuinely in use (as opposed to named in a diagram), and what the FastAPI rewrite concretely
bought over the original Streamlit script it replaced.

One request, traced end to end
------------------------------------

**Starting a run (``POST /experiments/start``).** ``api/routers/experiments.py``'s
``experiments_start`` builds an :class:`~core.domain.entities.ExperimentConfig` from the submitted
form, then calls ``ExperimentRunner.try_start`` (:mod:`core.services.experiment_runner`). That
method validates the config, checks the sanity cap on total generation calls, and -- under a
``threading.Lock`` -- flips a ``running`` flag and starts a daemon ``threading.Thread`` running the
actual generation loop. The HTTP handler returns immediately (202) with an SSE-connecting HTML
fragment; it never waits for a single response to be generated.

Inside that background thread, ``ExperimentRunner._run_one`` walks the same sequence for every
``student × archetype × bias × swept-value`` combination: build a prompt (optionally RAG-augmented
via :class:`~core.domain.interfaces.KnowledgeBase`), call ``LLMClient.generate`` (concretely
:class:`~core.adapters.ollama_client.OllamaClient`, a *synchronous* call to Ollama's native
``/api/chat``), then run the per-response cascade (CLAUDE.md SS3a; see :doc:`04-llm-analytics` for
the full story, including a real threshold-inversion finding): **Layer 0**
(:func:`core.analysis.response_classification.classify_response` -- deterministic
``VALID``/``EMPTY``/``MALFORMED_JSON``/``TRUNCATED``/``SCHEMA_ERROR`` gates) runs first; a
non-``VALID`` result short-circuits immediately, skipping both the NLP-metric computations and the
judge call. Only a ``VALID`` response reaches the three independent NLP-metric computations, which
now include a real sentence-embedding ``semantic_overlap``. **Layer 1**
(:func:`core.analysis.response_classification.is_echo_response`) then checks that
``semantic_overlap`` against the bias label -- an *implausibly high* score (not low) means the model
echoed its own instruction back instead of generating real conditioned text, and a synthesized
rejection ``JudgeVerdict`` is recorded without ever calling the real judge. Only a response that
clears both layers reaches ``Judge.evaluate`` (concretely
:class:`~core.adapters.structured_judge.StructuredJudge`, itself another synchronous LLM call, and
-- as of 2026-08-24 -- one that genuinely parses the judge's JSON instead of substring-matching
``"true"``). Cascade **Layer 2** (NLI/sentiment/toxicity classifiers) is not built; CLAUDE.md SS6
reserves it for the author to hand-write. Everything merges into one flat record (now including
``layer0_classification``/``layer1_echo_detected``/``v_confidence``/``v_rationale``) and persists via
``Repository.save_response`` (concretely :class:`~core.adapters.jsonl_store.JSONLStore`, which
appends one JSON line to ``results/lab_experiment_results/lab_export_<run_id>.jsonl``).

**Watching it happen (``GET /experiments/stream``).** This is where the architecture gets genuinely
interesting, not just layered. A background *thread* cannot safely hand data to an ``async`` request
handler's event loop by itself -- ``asyncio.Queue`` is not thread-safe. The one line that makes this
work is :func:`core.services._sse.bridge_to_queue`:

.. code-block:: python

   def bridge_to_queue(loop, queue, event) -> None:
       loop.call_soon_threadsafe(queue.put_nowait, event)

Every background-thread-driven progress mechanism in this project -- the real ``ExperimentRunner``
and Stage 1's throwaway ``DemoRunner`` alike -- shares this one function rather than each
reimplementing the thread/event-loop crossing. ``GET /experiments/stream`` is an ``async`` generator
that ``await``s ``queue.get()`` in a loop, wraps each item as a FastAPI-native
``ServerSentEvent``, and yields a distinctly-named terminal ``progress-done`` event once the run
ends -- so the client closes the connection deliberately, rather than relying on the browser's
default (and here undesirable) SSE auto-reconnect behavior.

**Why this isn't just `async def` all the way down.** The generation loop calls genuinely
synchronous, CPU- or network-blocking code at every step: ``ollama.Client.chat(...)`` (not
``ollama.AsyncClient``), and NLTK/TextBlob-based metric computation with no async equivalents.
Running that chain inside an ``async`` route handler directly would block FastAPI's single event
loop for the full duration of every generation call -- including blocking the *same* SSE stream
that's supposed to be reporting progress on it. The background thread exists specifically to isolate
blocking work the domain doesn't have an async-native way to do; the queue-bridge is the only
thread-safe channel back into the loop.

Architecture patterns actually in use
-------------------------------------------

**Dependency injection: module-level globals, not ``fastapi.Depends``.** FastAPI ships a built-in
``Depends()`` injection system; this project does not use it anywhere in ``api/routers/``. Instead,
every router constructs its concrete adapters as **module-level globals at import time** -- e.g.
``experiments.py``'s ``_runner = ExperimentRunner(llm_client=OllamaClient(), repository=JSONLStore(), ...)``,
and a separate ``_repository = JSONLStore()`` independently constructed in each of ``runs.py``,
``analytics.py``, ``clusters.py``, ``model_evo.py``, ``benchmark.py``, and ``nlp.py``. Tests swap
these directly by attribute assignment -- ``tests/integration/test_experiments_api.py``'s
``_fake_runner`` fixture does ``experiments._runner = ExperimentRunner(fakes["llm"], ...)`` for the
test's duration, then restores the original. This is simpler than FastAPI's own DI system for a
single-process, single-user app with no request-scoped session lifecycle to manage, and it lets
tests swap dependencies with a plain attribute assignment instead of ``app.dependency_overrides``.
The cost is real too: no per-request override scoping, no automatic teardown, and six routers each
building their own functionally-redundant ``JSONLStore()`` instance rather than sharing one. This is
a genuine, if implicit, tradeoff -- not FastAPI's intended pattern, chosen (or arrived at) because
nothing in this app's deployment shape needs what ``Depends()`` buys.

**Lazy singletons, with a documented bug in the caching itself.** ``experiments.py``'s
``_get_knowledge_base()`` is the concrete answer to "why does the model load once at startup, not per
request": ``RAGKnowledgeBase``'s underlying engine loads a ``SentenceTransformer`` model at
construction, a real multi-second cost not worth paying at import time for a feature (RAG) that's
optional per run. The function's own docstring records a real, since-fixed bug in this exact
caching: an earlier version assigned the module-level cache *before* confirming the load succeeded,
so a single failed load (e.g. an empty knowledge directory) permanently "poisoned" the cache --
every later RAG-enabled request silently reused the same broken, never-loaded instance, even after
the underlying problem was fixed, until the process itself was restarted. The fix reorders
construction so the cache is only assigned after a successful load; two regression tests
(``test_get_knowledge_base_does_not_cache_a_failed_load``,
``test_rag_enabled_with_unbuildable_knowledge_base_returns_400_not_500``) pin the corrected
behavior. The same "one instance for the process's lifetime" shape appears deliberately elsewhere --
``ExperimentRunner``'s own module-global ``_runner``, and Stage 1's ``DemoRunner`` module-global,
whose own docstring states the reason directly: "single-user/single-session per project
constraints," not an oversight.

**Layering is genuinely enforced, with one explained exception.** ``core/domain`` is confirmed
framework-agnostic by direct search, not just by its own claim: no import of ``fastapi``,
``jinja2``, or ``streamlit`` anywhere under it, and no import of ``core.adapters`` either -- the
interfaces genuinely don't reach down into their own implementations. The one thing ``core/domain``
does import that looks framework-adjacent is **pydantic**, and the entities module's own docstring
explains why this doesn't count as a violation: pydantic is a validation library, not a web
framework, and FastAPI itself is built on it -- so domain entities double as API request/response
DTOs without ``core.domain`` ever importing FastAPI to make that work. ``core/services`` was checked
the same way: it only ever type-hints against the ``core.domain.interfaces`` Protocols, never
imports a concrete adapter directly -- adapters are always handed in by whichever caller (a router,
or the CLI) assembled them.

**Concurrency model: one run, for the whole process, on purpose.** ``ExperimentRunner`` holds
exactly one ``threading.Lock`` and one ``running`` boolean -- instance-level state on the single
module-global ``_runner``, with no per-user or per-session keying anywhere. A second
``POST /experiments/start`` while a run is in flight is rejected outright (409 at the HTTP layer,
tested directly), not queued. This single-run guard is asserted as deliberate in several places'
own docstrings/comments ("single-user, single-session per the project's deployment constraints") --
worth noting precisely: that exact phrase is this codebase's own recurring gloss on CLAUDE.md's
stated context (a solo author, a bare-metal/no-cloud deployment target), not a sentence CLAUDE.md
itself contains verbatim. The design choice is real and load-bearing regardless of where the words
for it came from.

**``Repository`` has two implementations; only one is ever actually wired up.**
:class:`~core.adapters.sqlite_repo.SQLiteRepo` fully satisfies the ``Repository`` Protocol, has its
own complete unit-test suite (round-trip save/load, upsert-on-duplicate-run-id, multi-run isolation,
all against a real in-memory SQLite database via SQLAlchemy 2.0's typed ``DeclarativeBase`` style),
and exists specifically to normalize run-level metadata out of the ~21%-of-bytes duplication a real
JSONL export was found to contain. None of that changes the fact that every router and the CLI's own
``build_runner`` construct ``JSONLStore()`` directly -- ``SQLiteRepo`` is not imported by a single
live route or entry point today. This is a real, disclosed gap, not a hidden one: the interface
proves the abstraction is genuine (a real second implementation exists and passes the same
contract), the wiring simply hasn't caught up to it yet.

Frontend: server-rendered fragments, not a client app
------------------------------------------------------------

There is no client-side router, no bundler, and no build step anywhere in ``web/``. Every full page
under ``web/templates/`` is a complete, standalone HTML document; navigating between pages is a
plain full-page browser navigation via ``<a href="...">``, not a client-side route swap. A "partial
update" is htmx replacing one element's content with a **server-rendered** Jinja2 fragment -- e.g.
the live setup-summary panel on ``/experiments`` re-renders on every form change (debounced 300ms)
by POSTing the whole form to ``/experiments/preview`` and swapping the response into ``#task-preview``,
confirmed working end to end by a real-browser Playwright test, not just a unit test of the route.
Sub-tab switching (``web/static/tabs.js``) is the one deliberate exception -- all sub-tab content for
a page like ``/analytics`` renders in a single server response, and switching tabs is pure
client-side show/hide of already-rendered panels, with no additional network request per tab.

The SSE mechanism described above continues client-side through htmx's SSE extension
(``sse-connect``/``sse-swap``/``sse-close`` attributes, vendored as ``web/static/vendor/htmx/sse.js``):
the fragment returned by ``POST /experiments/start`` opens the ``EventSource`` and wires the inner
progress ``<div>`` to swap on each named event, closing itself on the terminal event the server sends.

**Two chart-rendering strategies exist because one library genuinely can't do what the other needs
to.** Most charts render via :func:`web.plotting.render.figure_to_div` -- a Plotly figure embedded as
a ``<div>`` + inline ``<script>``, interactive in the browser (hover, zoom, pan). A minority
-- specifically HDBSCAN's own minimum-spanning-tree and condensed-tree diagnostic plots inside the
Behavioral Topology view -- render via :func:`web.plotting.mpl_render.figure_to_img_tag` instead, a
static base64-encoded PNG. This isn't an inconsistency: those two plot types are matplotlib-only
methods on the ``hdbscan`` library's own clusterer object, with no Plotly equivalent to call
instead, confirmed directly in :mod:`web.plotting.cluster_charts`, where both calls are wrapped in a
``try/except`` because they can raise on certain real cluster geometries -- a plot failure there
degrades to "unavailable" rather than 500ing the whole page.

**No CDN, anywhere.** ``htmx.min.js``, its SSE extension, and ``plotly.min.js`` (~4.6 MB) are all
vendored locally under ``web/static/vendor/`` and served from this app's own process -- zero
``<script src="https://...">`` references exist in any template. This matches the project's
bare-metal, no-Docker, no-cloud deployment target directly: the app can run fully offline, with no
dependency on an external CDN's uptime or a reverse proxy's CSP allowlist, and no risk of an
unpinned CDN ``@latest`` silently shifting the frontend's behavior out from under a project whose
whole premise is reproducibility.

**A real tension: client-only preferences vs. server-baked chart colors.** The sidebar-collapse and
light/dark theme toggle (:doc:`../features`) are deliberately client-only, ``localStorage``-backed
preferences with no server round trip -- and a synchronous, blocking inline ``<script>`` in every
page's ``<head>`` applies the stored theme *before* the stylesheet paints, specifically to avoid a
flash of the wrong theme that a deferred script would cause. But Plotly/matplotlib charts are
rendered server-side with colors baked into static markup at request time, so a client-only
preference has no way to restyle a chart already on screen. The fix threads the preference through a
cookie the same inline script also writes (self-healing on every page load, not just on a toggle
click); every chart-serving router reads ``request.cookies.get("nn_lab_theme", "dark")`` and calls a
``set_chart_theme`` function before building that request's charts. That setter is a plain module-level
global in :mod:`web.plotting.render`/:mod:`web.plotting.mpl_render`, deliberately not made
thread-safe -- both modules' own comments justify this the same way the backend's single-run guard is
justified: acceptable under this project's own single-user, one-session-at-a-time constraint, not a
pattern that would hold up under concurrent multi-user traffic.

**Testing strategy follows directly from where real client-side logic actually lives.** Every page
except ``/experiments`` is tested through FastAPI's ``TestClient`` alone -- it never executes
JavaScript, so it can only verify server-rendered HTML, not client behavior. That's sufficient
everywhere else because ``/experiments`` is confirmed the only page carrying page-specific
conditional-field JavaScript (enabling/disabling the sweep sub-fields, dynamic per-parameter bounds,
self-critic/RAG/prompt-mode field interactions); every other template's script tags are limited to
the shared, page-agnostic ``tabs.js``/``ui.js`` plus vendored libraries. That is the reason a real
Playwright browser suite exists for exactly one page, not the whole app -- it is scoped to where a
"does this actually work in a browser" question can have a different answer than "does the server
return the right HTML."

Why this over the Streamlit monolith -- concretely, not aspirationally
------------------------------------------------------------------------------

The claimed benefits of splitting into ``core/domain → core/services → core/adapters`` behind
``api``/``web`` are independent process scaling, reusable logic without a UI, and testable business
logic. Two things in the actual codebase prove these are real, not just diagram labels:

- **``cli/run_experiment.py`` is zero-UI reuse, not a hypothetical.** Its ``build_runner`` wires the
  *exact same* concrete adapters (``OllamaClient``, ``JSONLStore``, ``NaivePromptStrategy``,
  ``StructuredJudge``) into the *same* ``ExperimentRunner`` class the FastAPI router uses -- its own
  docstring says so directly. The CLI drives the identical ``try_start``/``asyncio.Queue`` progress
  API the SSE endpoint drains, just printing to stdout instead of yielding server-sent events, with
  its own ``asyncio.run()`` wrapper supplying the event loop FastAPI would otherwise provide. There
  is no HTML, no routing, no web framework import anywhere in that file.
- **The service layer runs, and is tested, with no web framework present at all.**
  ``tests/unit/test_experiment_runner.py`` imports no ``fastapi``, starts no ``TestClient``, and
  runs no ``uvicorn`` -- it constructs ``ExperimentRunner`` directly against hand-written fakes and
  drives it with bare ``asyncio.run(scenario())`` calls. The integration test suite then reuses those
  *same* fake classes rather than redefining them for its own ``TestClient``-based tests -- one set
  of test doubles serves both a framework-free unit-test layer and a full-HTTP integration layer,
  which is only possible because the service layer never required a running server to begin with.

The original Streamlit script had none of this available to it by construction: a Streamlit app's
UI code and business logic run in the same process, on the same rerun-driven execution model, with
no equivalent to "start the generation logic with zero UI attached." Splitting the process is what
made the CLI possible as an afternoon's wiring exercise instead of a rewrite, and what let the
service layer's own tests stay independent of whichever front end (or none) happens to be driving it.
