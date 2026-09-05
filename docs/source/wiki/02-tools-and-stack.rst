02 — Tools, Stack, and Engineering Conventions
=================================================

This page answers a narrower question than :doc:`01-architecture`: not *how the pieces fit
together*, but *why this specific tool and not the obvious alternative*, for every layer of the
stack, and what coding conventions the project actually enforces (as opposed to aspires to).

Versions below are read directly from ``requirements-base.txt`` (the compiled lock file), not
``requirements.in``'s loose ``>=`` ranges — the lock file is what a fresh ``pip install`` actually
gets.

Backend stack
-----------------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Component
     - Version
     - Role / why this, not the obvious alternative
   * - FastAPI
     - 0.141.1
     - Async-native (required for the SSE live-progress endpoint, see
       :doc:`01-architecture`), Pydantic-native request/response validation that matches the
       project's own domain entities (:mod:`core.domain.entities` are themselves Pydantic
       ``BaseModel`` subclasses), and free auto-generated OpenAPI docs (``/docs``, ``/redoc``) --
       used directly as the project's live API reference rather than hand-maintained. Flask would
       need async support and an OpenAPI layer bolted on; Django's ORM/admin/auth machinery solves
       problems this single-user local tool doesn't have.
   * - Uvicorn
     - 0.48.0
     - The ASGI server FastAPI itself recommends; run directly (``uvicorn api.app:app --reload``),
       no process manager or app server in front of it -- appropriate for a bare-metal, single-user
       deployment target with no load to balance.
   * - Jinja2 + HTMX
     - 3.1.6 / vendored
     - See :doc:`01-architecture` for the full rationale (server-rendered fragments over a client
       SPA). No React/Vue, no npm/webpack/vite build step at all -- every static asset is either
       hand-written or vendored as a single ``.min.js`` file under ``web/static/vendor/``, so
       "deploy" is still just "run uvicorn," matching the no-Docker/no-cloud constraint.
   * - SQLAlchemy
     - 2.0.52
     - Used **synchronously**, not with an async driver -- a single-user local SQLite database has
       no concurrent-write contention to justify async I/O overhead. Uses the 2.0-native typed
       style (``DeclarativeBase``/``Mapped``/``mapped_column``), not the legacy ``declarative_base()``
       factory, because ``mypy`` cannot type-check the legacy factory's output without an extra
       plugin (found directly while running ``mypy`` against :mod:`core.adapters.sqlite_repo`
       during that adapter's own build).
   * - Ollama (python package)
     - 0.6.2
     - :class:`~core.adapters.ollama_client.OllamaClient` calls Ollama's **native** ``/api/chat``
       via this package, not the OpenAI-compatible endpoint the project used earlier -- the native
       endpoint is the only one that returns real per-call token counts and a
       load/prompt-eval/generation timing breakdown, confirmed by querying both endpoints live and
       diffing the raw JSON before switching. The judge (:mod:`core.adapters.structured_judge`) still
       goes through the OpenAI-compatible endpoint (:mod:`core.adapters._openai_compat`) on
       purpose -- performance telemetry is about the model being measured, not the judge doing the
       measuring, so there was no reason to touch a working, already-tested call site for a metric
       nothing asked of it.
   * - pydantic
     - 2.13.4
     - Backs every domain entity (:mod:`core.domain.entities`) and every FastAPI request/response
       body -- one validation library end to end, not a separate one for "the API layer" and
       another for "the domain layer."

LLM/analysis stack
-----------------------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Component
     - Version
     - Role / why this, not the obvious alternative
   * - scikit-learn
     - 1.8.0
     - Backs both the clustering fit-index math (``silhouette_score``, ``davies_bouldin_score``,
       ``adjusted_rand_score`` in :mod:`core.services.cluster_discovery`) and the baseline
       classifier in :mod:`core.analysis.model_evaluation` -- a single, well-tested numerical
       library for both jobs rather than a bespoke metric implementation, which matters directly
       for CLAUDE.md's own "measurement validity" framing: the *math* is borrowed and trusted, the
       *interpretation* (does this cluster correspond to a real archetype) is what's being tested.
   * - HDBSCAN
     - 0.8.43
     - Density-based clustering specifically because it doesn't force a fixed cluster count (unlike
       K-Means, which the project *also* runs separately as a deliberate point of comparison, not a
       replacement -- see :doc:`04-llm-analytics`). HDBSCAN's own condensed-tree/MST diagnostic
       plots are matplotlib-only with no Plotly equivalent, which is the direct reason this project
       has two separate chart-rendering paths at all (see :doc:`01-architecture`).
   * - umap-learn
     - 0.5.12
     - Dimensionality reduction ahead of HDBSCAN -- CLAUDE.md's own architecture note states raw
       linguistic features collapse into one indistinct cluster without it, i.e. UMAP isn't a
       cosmetic 2D-projection step, it's load-bearing for HDBSCAN finding any structure at all.
   * - NLTK
     - 3.9.4
     - Tokenization, POS tagging, and VADER sentiment across :mod:`core.analysis.nlp_science` and
       :mod:`core.analysis.neuro_metrics`. An older, less actively developed library than e.g.
       spaCy, kept specifically because it's what the original Streamlit prototype already used and
       every pinned-fixture metric test (CLAUDE.md SS7) was written against its exact tokenization
       behavior -- swapping tokenizers mid-project would silently change what every metric measures.
   * - sentence-transformers
     - 5.5.1
     - Backs the RAG knowledge-base retrieval (:mod:`core.adapters.rag.ingestion`), not the
       judge/metrics path -- see :doc:`04-llm-analytics` for exactly which metric (if any) uses
       embedding-based semantic similarity versus simpler token-overlap techniques.
   * - torch / torchvision
     - 2.5.1 / 0.20.1
     - Pinned with an **exact** ``==``, not the project's usual ``>=`` floor, and called out with a
       multi-line comment in ``requirements.in`` explaining why: a floating constraint here once let
       ``pip-compile`` silently resolve a newer, CPU-only default-PyPI build that clobbered the
       working CUDA install. This is a real incident, not a defensive guess -- see the *Real
       incidents* note below.

Documentation and reporting stack
--------------------------------------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Component
     - Version
     - Role / why this, not the obvious alternative
   * - Sphinx + myst-parser + sphinx-rtd-theme
     - 7.4.7 / 2.0.0 / 2.0.0 (theme)
     - RST is the project's native documentation format (31+ of the pages under ``docs/source/`` are
       ``.rst``); myst-parser exists specifically so the two FAQ pages (``faq_eng.md``/``faq_ua.md``)
       can stay in plain Markdown rather than being rewritten into RST for no reason -- it is a
       narrow exception, not a second parallel doc format. This page is written in RST to match the
       dominant convention, not the Markdown the FAQ pages happen to use. Theme switched 2026-08-24
       from ``furo`` to the Read the Docs theme (author's explicit choice); both were already pinned
       dependencies at that point, so the switch was a one-line ``conf.py`` change, not a new
       dependency.
   * - Allure (``allure-pytest``)
     - 2.16.0
     - Chosen over plain ``pytest-html`` alone specifically because Allure renders each test's own
       docstring as its displayed description in the report, not just the bare function name --
       directly serving CLAUDE.md SS7's stated goal ("Allure shows real descriptions, not bare
       names"), since this project's test suite doubles as portfolio evidence, not just a pass/fail
       gate.
   * - pytest-playwright
     - 0.9.0
     - The one real-browser dependency in the whole stack, deliberately scoped to ``tests/e2e``
       only -- see :doc:`01-architecture`'s frontend section for why only one page needs it, and
       :doc:`05-cicd` for why its process-isolation requirement shapes the tox/CI layout.

Testing conventions
------------------------

**Directory-encoded test taxonomy.** ``tests/`` is split into ``unit/``, ``integration/``,
``legacy_rag/``, and ``e2e/`` -- not an arbitrary grouping, but one enforced by a real, reproducible
bug: running ``tests/e2e`` before ``tests/unit`` in a single ``pytest`` invocation made ~20 unrelated
unit tests fail with ``RuntimeError: asyncio.run() cannot be called from a running event loop``,
because ``pytest-playwright``'s sync driver leaves the main-thread asyncio event loop unusable for
anything that later calls ``asyncio.run()`` directly (e.g. :mod:`core.services._sse`'s own bridge
tests). ``tox.ini``'s ``py312``/``linux``/``win32`` environments all pass ``--ignore=tests/e2e``; a
separate ``e2e`` environment runs Playwright alone. This is a process-isolation requirement forced
by a library interaction, not a stylistic preference for small folders -- see :doc:`05-cicd` for how
it shapes the proposed CI pipeline's job split.

**Pinned-fixture tests for borrowed math, not just business logic.** CLAUDE.md SS7 states plainly
that a metric imported from a third-party package is not assumed correct for this project's use --
e.g. ``zipf_deviation`` (:mod:`core.analysis.nlp_science`) is tested against a hand-computed RMSE on
a fixed, controlled word-frequency distribution (``tests/unit/test_nlp_science.py``), and
``compute_fit_indices`` (:mod:`core.services.cluster_discovery`) is tested against two perfectly
separated synthetic 2-point clusters where the correct silhouette/Davies-Bouldin answer is known in
advance (``tests/unit/test_cluster_discovery.py``). This is the direct, concrete form CLAUDE.md's
"measurement validity" claim takes in the test suite, not just a stated intention.

**Docstrings as documentation, not decoration.** NumPy-style docstrings (``Main Description`` /
``Parameters`` / ``Returns`` / ``Notes`` sections) are the project's one consistent dialect --
established in :mod:`core.analysis.data_contract` and :mod:`core.analysis.calculate_advanced_linguistic_metrics`
and followed since, because ``sphinxcontrib-napoleon`` renders this dialect directly into the
Sphinx API reference: a docstring here is also live documentation, not a comment that happens to sit
near a function signature.

Known, disclosed gaps (not silently fixed, not silently hidden)
-----------------------------------------------------------------------

- **No project-wide lint/type-check config -- resolved 2026-08-24.** ``mypy`` and ``ruff`` are
  pinned dev dependencies (``requirements-dev.in``), and until this date there was no
  ``pyproject.toml``, ``mypy.ini``, or ``.ruff.toml`` anywhere in the repository, and no dedicated
  ``tox -e`` environment ran either tool. This is now closed for real, not just documented around: a
  single ``pyproject.toml`` holds ``[tool.black]``/``[tool.ruff]``/``[tool.mypy]`` config, and
  ``tox -e lint`` runs ``ruff check .`` + ``mypy core api cli web utils`` with the exact same tool
  versions pinned in ``requirements-dev.in`` (``ruff==0.15.17``, ``mypy==2.1.0`` -- an unpinned
  first attempt pulled a newer ``ruff`` with a different default rule set inside the isolated tox
  env, a live demonstration of why this project pins tool versions everywhere else too). All three
  tools' scope deliberately excludes the untouched Neo4j subsystem (CLAUDE.md SS1) and the
  legacy/undecided ``streamlit_app*`` variants (SS5/SS12) -- the same paths ``.coveragerc`` already
  omits from coverage measurement, kept consistent across every tool rather than each one inventing
  its own scope. ``black`` itself was also run for the first time across every in-scope file: 86 of
  119 live-code files had never been formatted (52 remained in scope after the legacy/Neo4j
  exclusion), applied as one repo-wide pass and confirmed against the full regression suite before
  and after -- but ``black`` is deliberately **not** wired into ``tox -e lint`` as a gate; running
  the formatter once and gating on it in CI going forward are two separate decisions, and only the
  first has been made so far. See :doc:`05-cicd` for what a GitHub Actions pipeline would still need
  to add to make this a real, automated gate rather than a manually-invoked ``tox -e lint``.
- **``requirements-linux.txt``/``requirements-windows.txt`` are platform-specific compiled lock
  files** generated from the same ``requirements.in`` (plus a platform overlay file) on their
  respective OS -- ``requirements-linux.txt`` in particular can only be regenerated by running
  ``pip-compile`` on an actual Ubuntu machine, since ``pip-compile`` resolves against the *running*
  platform's wheel availability, not a target platform flag. ``requirements-windows.txt`` is
  deliberately empty (Windows installs PyTorch via a custom index URL instead, see
  :doc:`../roadmap`'s environment setup) -- not dead weight, a documented placeholder. See
  :doc:`03-feature-implementation`'s technical-debt section for a *different*, genuinely stray
  ``requirements.txt`` found alongside these two, which is not part of this documented split.
- **``requirements-linux.txt`` is stale, confirmed 2026-08-24, real risk to CLAUDE.md SS2's
  bare-metal-Ubuntu deployment target -- not yet fixed.** Its last modification date is
  2026-06-22, two months before the FastAPI rewrite (Stage 0 onward, 2026-08-21+) added ``fastapi``,
  ``sqlalchemy``, and roughly 30 other packages (the full docs/testing toolchain -- ``sphinx``,
  ``allure-pytest``, ``pytest-cov``, ``pytest-playwright``, ``pandas-stubs``, ...) to
  ``requirements.in`` -- confirmed directly: neither ``fastapi`` nor ``sqlalchemy`` appears anywhere
  in ``requirements-linux.txt`` today. The documented Ubuntu install command combines both files in
  one ``pip install`` call, which risks the exact same class of version-conflict failure this
  session already hit twice on ``requirements-dev.txt`` (see the roadmap's found-after-the-fact log,
  2026-08-22/2026-08-23 entries) when a stale and a current lock file are installed together. **This
  whole entire FastAPI rewrite has not been run or tested on real Linux at any point during its
  construction** -- every stage's manual verification in :doc:`../roadmap` was performed on Windows.
  The application code itself shows no obvious cross-platform red flags on inspection (no hardcoded
  backslash paths, no unguarded ``os.name``/``platform.system()`` branches in ``core``/``api``/
  ``web``/``cli``; path handling goes through ``pathlib``/``api/_paths.py`` throughout), but that is
  a code-review finding, not a substitute for actually running it on Ubuntu. Fix requires an actual
  Ubuntu machine (``pip-compile requirements.in --output-file=requirements-linux.txt``, then a real
  ``uvicorn``/``pytest`` run there) -- author's explicit decision, 2026-08-24: document this honestly
  rather than have the AI agent provision a WSL distro to verify it in this session.

Real incidents this project's own history documents (why the discipline above exists)
-------------------------------------------------------------------------------------------

Two concrete, previously-observed failures directly justify the "never hand-edit the compiled
``requirements-*.txt`` files, always regenerate via ``pip-compile``" rule stated in CLAUDE.md SS11:

1. A plain ``pip install -r requirements-base.txt --upgrade`` once silently replaced a working CUDA
   build of torch (``2.5.1+cu121``) with a CPU-only build (``2.12.0+cpu``) -- no explicit "remove
   GPU support" step was taken, a floating version constraint alone did it. Fixed by pinning
   ``torch``/``torchvision`` exactly, as shown in the stack table above.
2. A committed ``requirements-dev.txt`` was found to have drifted back into an unconstrained
   resolution twice, each time reintroducing an entire Linux-oriented ``nvidia-cuda-*``/``cuda-toolkit``
   dependency chain that has no Windows wheel -- and, on one recompile, a *different* unconstrained
   resolution of ``transformers``/``safetensors`` landed on a version combination that reliably
   segfaulted inside ``pandas``' pyarrow-backed string handling whenever ``sentence_transformers``
   had been imported earlier in the same process (exactly what every test run does, via
   ``tests/conftest.py``'s module-level RAG fixture). The fix in both cases was the same:
   ``pip-compile requirements-dev.in --output-file=requirements-dev.txt -c requirements-base.txt``,
   constraining the dev lock file to the already-proven-working base lock file instead of letting
   ``pip-compile`` re-resolve shared packages independently against whatever PyPI serves at compile
   time.
