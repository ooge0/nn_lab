Features
========

What actually works right now, as of Stage 9 of the FastAPI rewrite --
distinct from :doc:`architecture` (structure) and the auto-generated API
reference (mechanical class/method listing). Each section says whether the
feature is reachable through the *running app* today or is backend-only,
verified through tests (and, where noted, a direct manual check) but not
yet wired to an endpoint.

Live progress via Server-Sent Events
-------------------------------------

**Reachable now:** yes -- ``GET /demo``.

A background thread runs a task and streams progress back to the browser
via ``EventSourceResponse`` (FastAPI's built-in SSE support), replacing
Streamlit's rerun-based UI model. Includes a concurrent-run guard (rejects
a second run while one is in flight -- this is a single-user app) and a
clean client-side close signal (``sse-close``) so the browser's
``EventSource`` doesn't auto-reconnect after the run finishes.

Currently wired to a throwaway dummy counter (:mod:`core.services
._demo_runner`), not real generation -- proving the mechanism in isolation
before Stage 5 replaces it with the real experiment runner.

See :mod:`api.routers.demo`, :mod:`core.services._demo_runner`.

Run a full experiment (``ExperimentRunner``)
-----------------------------------------------

**Reachable now:** yes -- ``GET /experiments``.

Full ``tab_gen`` parity: every (student x archetype x bias x
swept-value) combination, judged, optionally RAG-augmented, with a live
task-count preview before you commit. A single declared experiment can
mean many generation calls -- ``total_tasks = students x archetypes x
biases x sweep_steps`` -- so a hard sanity cap
(``config.ini``'s ``[EXPERIMENT] max_total_tasks``, 500 by default)
refuses an oversized request with HTTP 413 before any generation starts,
rather than just showing a skippable preview the way the legacy app does.

Verified end to end against a real local Ollama server, including
self-critic mode (judge correctly routed to the student model) and a
2-step temperature sweep: a capable model (``qwen:latest``) produced a
real response for one sweep value and echoed the prompt's own placeholder
template for the other -- a live demonstration that the *same* model
isn't reliably consistent, and that the judge's own verdict varied
between the two calls even where the outputs were textually identical
(real LLM sampling variance in the judge call itself, not a bug --
exactly the kind of fragility CLAUDE.md SS4 flags "naive judge" for).

See :mod:`core.services.experiment_runner`, :mod:`api.routers.experiments`.

**UI usability pass (post-Stage-16):** the form's ``student_models``/``archetypes`` multi-selects
are now ``required`` -- submitting with neither selected used to silently produce a valid-but-empty
0-task "run" (``ExperimentConfig`` has no minimum-length constraint on either field, so nothing
server-side ever caught it) instead of a clear message. The live-progress view gained a real HTML5
``<progress>`` element -- previously the whole "progress bar" was one line of plain text with no
visual indicator at all, not a styling gap. On completion it now also links directly to
``/runs``/``/analytics``/``/nlp``/``/clusters`` -- previously the only way to see a result was to
already know to navigate to one of those pages and pick the run from its dropdown by hand. All of
``web/``'s pages gained a shared, minimal stylesheet (``web/static/style.css``) -- CLAUDE.md SS2
keeps the frontend deliberately thin ("may be rough"), but every page had *zero* CSS before this,
not just plain -- unstyled native form controls read as broken to a real user, not merely austere.
See :doc:`operations` for a full UI + API walkthrough exercising all of this against a real run.

**Stopping a run early (``POST /experiments/stop``):** restores a real feature the legacy sidebar
had (``streamlit_app.py``'s "Stop generation" button, ``trigger_stop``/``stop_requested``) that was
dropped during the rewrite and had no replacement at all until now -- confirmed found, not assumed,
by reading the legacy code directly after the author asked "how do I stop a run" and got no answer
from either the UI or the API. :meth:`~core.services.experiment_runner.ExperimentRunner.request_stop`
is **cooperative, not preemptive**: a ``threading.Event`` checked only *between* tasks in the main
loop, not mid-generation-call -- a response already in flight when stop is requested always finishes
and gets persisted first, since safely aborting a call already in progress would need deeper changes
to the ``LLMClient`` adapters themselves. The Stop button (rendered inline in the live SSE progress
fragment, gone once the run reaches a terminal state) and the raw API (``POST /experiments/stop`` --
200 with a confirmation if a run was actually running, 409 if there was nothing to stop) both verified
end to end against real local Ollama: a 6-task run against ``tinyllama:latest`` stopped after
exactly 1 completed response when asked to stop ~1 second in, with a real ``stopped`` terminal SSE
event (distinct from ``done``) and a real partial-results JSONL file on disk.

See :mod:`core.services.experiment_runner`, :mod:`api.routers.experiments`.

Real bug found and fixed while wiring the metrics merge
-------------------------------------------------------------

Three of the per-response metrics
(:mod:`~core.analysis.nlp_science`/:mod:`~core.analysis.neuro_metrics`/
:mod:`~core.analysis.calculate_advanced_linguistic_metrics`) are computed
*twice*, independently, under the *same* key name: ``self_focus`` (two
different pronoun sets) and ``word_count``/``ms_per_word`` (NLTK
tokenization vs. a naive whitespace split). The legacy app's plain
``entry.update(...)`` merge silently lets whichever computation runs last
win -- confirmed on real text losing the more accurate value in favour of
a wrong ``0.0``. ``neuro_metrics.py`` already suffixes six of its seven
other overlapping fields with ``_ext`` for exactly this reason; this was
the one case the convention wasn't applied to. Fixed at the merge point in
``ExperimentRunner`` (not by touching the pre-existing metric modules
themselves): both values now survive, under ``self_focus``/``self_focus_ext``
and ``word_count``/``word_count_raw``/``ms_per_word``/``ms_per_word_raw``.

Ollama generation (``LLMClient``)
------------------------------------

**Reachable now:** yes, via ``/experiments`` above. Verified with
automated tests *and* real calls against a local Ollama server across
multiple models.

:class:`~core.adapters.ollama_client.OllamaClient` calls Ollama's **native**
API (``/api/chat``, via the official ``ollama`` Python package), not the
OpenAI-compatible endpoint the legacy app and this adapter both used
originally -- switched specifically to capture real per-call performance
data the compat endpoint doesn't expose at all (confirmed by querying both
live and comparing the raw JSON, not assumed): real token counts
(``prompt_tokens``/``completion_tokens``, from Ollama's own
``prompt_eval_count``/``eval_count``) and a genuine timing breakdown
(``ollama_total_duration_ms``/``ollama_load_duration_ms``/
``ollama_prompt_eval_duration_ms``/``ollama_eval_duration_ms``, converted
from Ollama's native nanosecond fields). :class:`~core.services
.experiment_runner.ExperimentRunner` derives a real ``tokens_per_second``
from these (``completion_tokens`` / ``ollama_eval_duration_ms``) -- an
actual measurement, not the ``ms_per_word`` proxy (wall-clock duration over
a word count) every response still also gets, which stays meaningful for
any future non-Ollama backend that can't report this. Host is derived from
the same ``config/config.ini`` ``[OLLAMA]`` value the judge still uses
(``openai_base_url``, with its ``/v1`` suffix stripped), not a second config
entry that could drift out of sync. Still implements the :class:`~core.domain
.interfaces.LLMClient` interface unchanged, so callers depend on the
interface, not on Ollama or its transport specifically.

One real, non-obvious finding from testing this live: on a fresh client,
the *first* call's client-measured wall-clock (``duration_ms``) can run
seconds longer than Ollama's own self-reported ``ollama_total_duration_ms``
-- a one-time connection-establishment cost, not a per-call pattern
(confirmed by calling three times in a row: the gap was ~2000ms on the
first call, ~1-2ms on the next two).

The naive judge still calls the OpenAI-compatible endpoint via
:mod:`core.adapters._openai_compat`, unchanged -- performance telemetry is
about the student model being measured, not the judge doing the measuring.

See :mod:`core.adapters.ollama_client`, :mod:`core.adapters._openai_compat`.

Structured judge and the Layer 0/1/2 cascade
-----------------------------------------------

**Reachable now:** yes, via ``/experiments`` above (routes to the student
model in self-critic mode, the teacher model otherwise -- teacher_model is
required unless self-critic is on, validated before any generation
starts).

As of 2026-08-24, every response passes through a real, ordered cascade
before ``entry`` is persisted (CLAUDE.md SS3a) -- not a single monolithic
judge call:

1. **Layer 0** (:func:`core.analysis.response_classification.classify_response`)
   -- deterministic gates: ``VALID`` / ``EMPTY`` / ``MALFORMED_JSON`` /
   ``TRUNCATED`` / ``SCHEMA_ERROR``. A non-``VALID`` response short-circuits
   immediately -- no metrics, no judge call.
2. **Layer 1** (:func:`core.analysis.response_classification.is_echo_response`)
   -- a narrow, embedding-based echo detector: rejects a response whose
   ``semantic_overlap`` (cosine similarity to the bias label) is
   *implausibly high*, not low -- the inverse of standard STS intuition,
   calibrated against this project's own real generated data. See
   :doc:`wiki/04-llm-analytics` for the full cause-and-effect story. An echo
   synthesizes a rejection ``JudgeVerdict`` without calling the real judge.
3. **Layer 3** (:class:`~core.adapters.structured_judge.StructuredJudge`) --
   only reached for a ``VALID``, non-echo response. Replaces the former
   ``NaiveJudge``, which asked for structured JSON but then checked
   ``"true" in response_text.lower()`` instead of parsing it -- a malformed
   response was silently indistinguishable from a genuine "no".
   ``StructuredJudge`` genuinely parses ``{verdict, confidence, rationale}``;
   a parse failure now resolves to a *distinguishable* ``rationale``
   ("...not valid JSON...") instead of a silent false negative.

Cascade **Layer 2** (:func:`core.analysis.hallucination_check.check_hallucination`, added
2026-08-24) is a real NLI factual-contradiction check against RAG-retrieved context -- but only
meaningful, and only run, when RAG is enabled for the run (there is no general-purpose ground-truth
document to check "hallucination" against otherwise). Unlike Layers 0/1, it is deliberately
**non-gating**: it computes and persists a real predicted label and contradiction score, but does
not reject responses or affect ``v_ok`` -- no real-data-calibrated rejection threshold exists yet
for it, the same discipline that caught Layer 1's threshold needing to be inverted before it shipped
(see :doc:`wiki/04-llm-analytics`). Turning it into a gate is deferred to the author's own future
review of real RAG-enabled run data.

Persisted entries carry ``layer0_classification``, ``layer1_echo_detected``, ``layer2_checked``,
``layer2_predicted_label``, ``layer2_contradiction_score``, ``v_confidence``, ``v_rationale``
alongside the existing ``v_ok``.

See :mod:`core.analysis.response_classification`, :mod:`core.analysis.hallucination_check`,
:mod:`core.adapters.structured_judge`, :class:`core.domain.interfaces.Judge`.

Persistence (``Repository``)
--------------------------------

**Reachable now:** ``JSONLStore`` yes, via ``/experiments`` above (every
generated response lands in ``results/lab_experiment_results/``).
``SQLiteRepo`` no -- backend only, tested, not yet wired to an endpoint.

Two interchangeable implementations of :class:`~core.domain.interfaces
.Repository`:

- :class:`~core.adapters.jsonl_store.JSONLStore` -- one JSONL file per run,
  same directory/naming convention as the legacy "Save JSONL" button, but
  appends per response rather than buffering everything in memory until a
  manual save click (a deliberate improvement -- a crash mid-run no longer
  loses everything).
- :class:`~core.adapters.sqlite_repo.SQLiteRepo` -- SQLAlchemy 2.0,
  normalizes run metadata into its own table instead of repeating it on
  every response row. Motivated directly by a real-data finding: in a
  sampled legacy export, 21.3% of every row's bytes were exactly-repeated
  run-level fields.

See :mod:`core.adapters.jsonl_store`, :mod:`core.adapters.sqlite_repo`.

Response record fields
~~~~~~~~~~~~~~~~~~~~~~~~~~

The full field set of one persisted response record, pulled directly from a real entry generated
by a live run (``ExperimentRunner._run_one``, Stage 6, extended with real Ollama performance
telemetry after Stage 8, the Layer 0/1 cascade fields, and the Layer 2/social-focus/hedging/
dependency-distance fields, both added 2026-08-24) -- 77 keys today, confirmed via a direct entry
count, not estimated. Kept here, next to the storage layer that persists these records, rather than
as a separate schema page.

.. list-table::
   :widths: 15 20 65
   :header-rows: 1

   * - Category
     - Key
     - Description
   * - Run/task metadata
     - ``batch``
     - Timestamp string when this response was generated
   * - Run/task metadata
     - ``total_tasks``
     - Total generation tasks in the whole run
   * - Run/task metadata
     - ``steps``
     - Current step number (int)
   * - Run/task metadata
     - ``step``
     - Same, as legacy-matching ``"N/total"`` string
   * - Run/task metadata
     - ``strategy``
     - Prompt construction mode (``Tuned``/``Blind``/``Raw``)
   * - Run/task metadata
     - ``archetype``
     - Behavioral archetype this response was conditioned on
   * - Run/task metadata
     - ``bias``
     - Bias descriptor(s) injected into the prompt
   * - Run/task metadata
     - ``system_prompt``
     - The actual system prompt sent to the model
   * - Run/task metadata
     - ``archetype_about``
     - Human-readable description of the archetype
   * - Run/task metadata
     - ``student``
     - The model being evaluated (generator)
   * - Run/task metadata
     - ``teacher``
     - Judge model (same as ``student`` if self-critic)
   * - Run/task metadata
     - ``sweep_param``
     - Which parameter was swept (``"Baseline"`` if none)
   * - Run/task metadata
     - ``val``
     - The swept parameter's value for this response (or base temperature if no sweep)
   * - Judge verdict
     - ``layer0_classification``
     - Layer 0 result: ``VALID`` / ``EMPTY`` / ``MALFORMED_JSON`` / ``TRUNCATED`` / ``SCHEMA_ERROR``
   * - Judge verdict
     - ``layer1_echo_detected``
     - ``True`` if Layer 1 rejected the response as an echo of its own bias/archetype instruction (real judge call skipped)
   * - Judge verdict
     - ``layer2_checked``
     - Added 2026-08-24. ``True`` only when RAG was enabled and both texts were non-empty -- Layer
       2's NLI check needs retrieved context to check consistency against
   * - Judge verdict
     - ``layer2_predicted_label``
     - Added 2026-08-24. NLI cross-encoder's argmax label: ``contradiction`` / ``entailment`` /
       ``neutral``, or ``None`` if not checked. Logged only -- does not affect ``v_ok`` (no
       real-data-calibrated rejection threshold exists yet, unlike Layer 1)
   * - Judge verdict
     - ``layer2_contradiction_score``
     - Added 2026-08-24. Softmax probability, ``0.0``-``1.0``, or ``None`` if not checked
   * - Judge verdict
     - ``v_ok``
     - Pass/fail from the cascade (Layers 0/1 short-circuit, else ``StructuredJudge``) (bool)
   * - Judge verdict
     - ``v_ok_numeric``
     - Same, as 0/1 (for aggregation/heatmaps)
   * - Judge verdict
     - ``v_confidence``
     - Judge's stated confidence, ``0.0``-``1.0`` (``None`` if the judge didn't supply one; ``1.0`` for a synthesized Layer 0/1 rejection)
   * - Judge verdict
     - ``v_rationale``
     - One-sentence explanation -- a real judge rationale, a Layer 0/1 rejection reason, or a parse-failure explanation (never silently blank)
   * - Generation output & timing
     - ``output``
     - The model's generated text (post-extraction)
   * - Generation output & timing
     - ``duration_ms``
     - Client-side wall-clock generation time
   * - Generation output & timing
     - ``validation_duration_ms``
     - Time spent on the judge call
   * - Ollama performance telemetry
     - ``prompt_tokens``
     - Real prompt token count, from Ollama's own ``prompt_eval_count``
   * - Ollama performance telemetry
     - ``completion_tokens``
     - Real response token count, from Ollama's own ``eval_count``
   * - Ollama performance telemetry
     - ``ollama_total_duration_ms``
     - Ollama's self-reported total call time
   * - Ollama performance telemetry
     - ``ollama_load_duration_ms``
     - Time spent loading the model into memory
   * - Ollama performance telemetry
     - ``ollama_prompt_eval_duration_ms``
     - Time spent processing the prompt
   * - Ollama performance telemetry
     - ``ollama_eval_duration_ms``
     - Time spent actually generating tokens
   * - Ollama performance telemetry
     - ``tokens_per_second``
     - Derived: ``completion_tokens / (ollama_eval_duration_ms / 1000)`` -- real throughput
   * - RAG
     - ``rag_enabled``
     - Whether retrieval was used for this response
   * - RAG
     - ``rag_mode``
     - Retrieval query strategy, ``None`` if disabled
   * - RAG
     - ``rag_top_k``
     - Chunks requested, ``None`` if disabled
   * - RAG
     - ``rag_query``
     - The actual retrieval query text
   * - RAG
     - ``rag_chunks_count``
     - Chunks actually retrieved
   * - RAG
     - ``rag_context_chars``
     - Length of injected RAG context
   * - RAG
     - ``rag_context``
     - The injected RAG context text
   * - Sampling parameters (static, run-level)
     - ``val_temperature``, ``val_top_p``, ``val_frequency_penalty``, ``val_presence_penalty``
     - The configured base sampling values -- unconditionally persisted regardless of what (if
       anything) was swept
   * - Linguistic (``PsychScientist``)
     - ``sentiment``
     - Overall VADER sentiment score
   * - Linguistic (``PsychScientist``)
     - ``sentiment_variance``
     - Sentence-to-sentence sentiment volatility
   * - Linguistic (``PsychScientist``)
     - ``subjectivity``
     - TextBlob subjectivity score
   * - Linguistic (``PsychScientist``)
     - ``lexical_density``
     - Ratio of content words to total words
   * - Linguistic (``PsychScientist``)
     - ``corrected_ttr``
     - Corrected type-token ratio (vocabulary diversity)
   * - Linguistic (``PsychScientist``)
     - ``readability_ari``
     - Automated Readability Index
   * - Linguistic (``PsychScientist``)
     - ``avg_sentence_length``
     - Average words per sentence
   * - Linguistic (``PsychScientist``)
     - ``word_count``
     - NLTK-tokenized word count -- the canonical value after Stage 6's collision fix (see
       ``word_count_raw`` below)
   * - Linguistic (``PsychScientist``)
     - ``ms_per_word``
     - Generation time / ``word_count`` -- the word-count-based velocity proxy every backend can
       compute, regardless of what it reports (compare ``tokens_per_second`` above, the real
       measurement for Ollama-backed runs)
   * - Linguistic (``PsychScientist``)
     - ``self_focus``
     - Ratio of self-referential pronouns (broad set) -- the canonical value after Stage 6's
       collision fix
   * - Linguistic (``PsychScientist``)
     - ``social_focus``
     - Ratio of second/third-person pronouns (you/he/she/they/...) -- added 2026-08-24 to give
       ``self_focus`` the deictic contrast it was missing (I-focus vs. social-focus)
   * - Linguistic (``PsychScientist``)
     - ``modality``
     - Ratio of modal-verb words (must/should/could/etc.)
   * - Linguistic (``PsychScientist``)
     - ``hedge_ratio``
     - Ratio of epistemic-hedge words (might/perhaps/seem/...) -- Hyland (2005) metadiscourse
       category, added 2026-08-24
   * - Linguistic (``PsychScientist``)
     - ``booster_ratio``
     - Ratio of certainty-booster words (definitely/always/absolutely/...) -- same Hyland (2005)
       framework's counterpart to ``hedge_ratio``, added 2026-08-24
   * - Linguistic (``PsychScientist``)
     - ``cognitive_density``
     - Ratio of cognitive-process verb words (think/believe/analyze/etc.)
   * - Linguistic (``PsychScientist``)
     - ``repetition_score``
     - Frequency of the single most-common word / total words
   * - Linguistic (``PsychScientist``)
     - ``abstract_ratio``
     - Ratio of abstract vs. concrete words (WordNet-based)
   * - Linguistic (``PsychScientist``)
     - ``pos_distribution``
     - Dict of part-of-speech proportions (NOUN/VERB/ADJ/ADV)
   * - Linguistic (``PsychScientist``)
     - ``zipf_deviation``
     - Normalized RMSE vs. Zipf's-law-expected word-frequency curve
   * - Psycholinguistic (``NeuroMetrics``)
     - ``rigidity``
     - Proportion of *all* repeated tokens (not just the top one -- distinct from
       ``repetition_score``)
   * - Psycholinguistic (``NeuroMetrics``)
     - ``sentiment_variance_ext``
     - Neuro module's own sentiment-volatility computation (kept separate from
       ``sentiment_variance`` after the Stage 6 collision fix)
   * - Psycholinguistic (``NeuroMetrics``)
     - ``abstract_ratio_ext``
     - Neuro module's own abstract-word ratio (narrower word list than ``abstract_ratio``)
   * - Psycholinguistic (``NeuroMetrics``)
     - ``modality_ext``
     - Neuro module's own modal-word ratio (narrower set than ``modality``)
   * - Psycholinguistic (``NeuroMetrics``)
     - ``cognitive_load``
     - Composite: (avg sentence length + punctuation density + subordinator ratio) / 3
   * - Psycholinguistic (``NeuroMetrics``)
     - ``coherence``
     - TF-IDF cosine similarity between consecutive sentences
   * - Psycholinguistic (``NeuroMetrics``)
     - ``self_focus_ext``
     - Neuro module's own self-pronoun ratio (narrower set than ``self_focus``)
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``levenshtein_dist``
     - Edit distance from input prompt to output
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``semantic_overlap``
     - Sentence-embedding cosine similarity, input vs. output (``all-MiniLM-L6-v2``) -- fixed
       2026-08-24 from a plain Jaccard token-overlap that this field's name never actually
       described; see :doc:`wiki/04-llm-analytics`
   * - Syntactic (``syntactic_complexity``)
     - ``dependency_distance``
     - Mean dependency-tree distance between related token pairs (spaCy + TextDescriptives) --
       added 2026-08-24, a validated complexity marker independent of raw sentence length
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``expansion_ratio``
     - Output word count / input word count
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``punc_density``
     - Punctuation characters / word count
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``unique_ratio``
     - Unique words / total words
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``word_count_raw``
     - Naive ``.split()``-based word count (the losing side of Stage 6's collision fix --
       ``word_count`` above is the NLTK-based canonical value)
   * - Shared (``calculate_advanced_linguistic_metrics``)
     - ``ms_per_word_raw``
     - Same collision situation for ``ms_per_word``

See :mod:`core.services.experiment_runner`, :mod:`core.analysis.nlp_science`,
:mod:`core.analysis.neuro_metrics`, :mod:`core.analysis.calculate_advanced_linguistic_metrics`.

RAG knowledge retrieval (``KnowledgeBase``)
-----------------------------------------------

**Reachable now:** yes, via ``/experiments``'s RAG toggle -- built and
loaded lazily on first RAG-enabled request (its ``SentenceTransformer``
model load is a real multi-second cost, not worth paying at every app
start for an optional, per-run feature).

:class:`~core.adapters.rag.knowledge_base.RAGKnowledgeBase` wraps
:class:`~core.adapters.rag.ingestion.RAGEngine` (FAISS + Sentence
Transformers) behind the :class:`~core.domain.interfaces.KnowledgeBase`
interface. The whole RAG module moved from ``core/rag/`` to
``core/adapters/rag/`` in Stage 3, with every import across the live
``streamlit_app*.py`` entry points updated so the legacy app kept working
throughout the move.

See :mod:`core.adapters.rag.knowledge_base`, :mod:`core.adapters.rag.ingestion`.

Prompt construction (``PromptStrategy``)
---------------------------------------------

**Reachable now:** yes, via ``/experiments`` above (mode is selectable --
Tuned / Blind / Raw). Also tested in isolation with pinned expected
outputs.

:class:`~core.adapters.prompt_strategy.NaivePromptStrategy` ports the
three system-prompt construction modes (Tuned / Blind / Raw) from the
*real* per-iteration generation code, not the separate UI preview code
(which turned out to differ -- see below).

One legacy bug found and *not* carried forward: the "Exclude archetype
from prompt" checkbox only ever affected the UI preview text; it was never
read by the real generation code, so it silently did nothing in the live
app. This adapter's ``exclude_archetype_from_prompt`` parameter actually
works, implementing the checkbox's evident intent.

See :mod:`core.adapters.prompt_strategy`.

Run summary (``MetricsEngine``)
-----------------------------------

**Reachable now:** yes -- ``GET /runs``.

Read-only aggregation over one run's persisted responses: record/step
counts, sweep parameter and value range, timing averages, and
teacher/student/prompt-strategy/archetype/bias/RAG summaries -- the same
``summary_data`` shape as the legacy ``tab_perf``. A run picker
(``<select>``) htmx-swaps in ``GET /runs/summary``'s fragment for whichever
run is selected, defaulting to the most recently started one. Verified
against real Ollama-generated runs, including one spanning two archetypes.

One legacy display bug is *not* carried forward: ``tab_perf`` shows the
sweep-configuration widget's ``steps`` value on its "Steps" row rather than
the data it actually computes (``steps_count``) and then discards -- this
engine only ever sees persisted data, so there's no live widget value to
substitute in the first place.

See :mod:`core.services.metrics_engine`, :mod:`api.routers.runs`.

Navigation
--------------

**Reachable now:** yes -- ``GET /``.

Found while answering a question about how to actually reach ``/runs`` from the running app: there
was no navigation anywhere. ``/experiments`` had no link to ``/runs``, ``/runs`` had exactly one
conditional link back to ``/experiments``, and the app's own root (``/``) 404'd -- every page was
only reachable by knowing its exact URL in advance. Fixed with a shared ``_nav.html`` partial
(included on ``/experiments`` and ``/runs``) and a new landing page at ``/`` linking to
``/experiments``, ``/runs``, and the live Swagger/ReDoc docs. Deliberately not added to ``/demo``,
which documents itself as throwaway Stage-1 scaffolding, not a real page.

Service status (Ollama/NLTK reachability)
------------------------------------------------

**Reachable now:** yes -- ``GET /status`` (JSON), ``GET /status/widget`` (HTML fragment, embedded on
``/experiments``).

The FastAPI-era equivalent of the legacy sidebar's three green/red buttons (Ollama/NLP/Neo4j) --
deliberately scoped to **Ollama + NLTK only** (author's explicit choice): the whole Neo4j subsystem
stays "not even import-path-touched" per CLAUDE.md SS1, and wiring a new status check into it would
itself be a new integration point into that untouched subsystem, not just a read. Real checks, not
the legacy pattern: ``check_nltk()`` never calls ``nltk.download()`` (the legacy
``ensure_nltk_resources()`` silently downloaded anything missing, which meant its own "NLP ❌" branch
was unreachable dead code -- confirmed by reading it, not assumed) -- a missing resource is reported
honestly instead of silently fixed and hidden. ``check_ollama()`` reuses
:func:`core.adapters.ollama_client._native_host`'s host resolution rather than a second, possibly-
drifting config value. See :mod:`core.services.status_checks`, :mod:`api.routers.status`.

Behavioral analytics (``tab_analytics``)
--------------------------------------------

**Reachable now:** yes -- ``GET /analytics``.

Three sub-tabs of Plotly charts over one run's persisted responses, ported
from the legacy ``tab_analytics`` with no new metric computation -- every
field charted (``v_ok_numeric``, ``duration_ms``, ``word_count``,
``ms_per_word``, ``unique_ratio``, ``levenshtein_dist``,
``semantic_overlap``, ``punc_density``, ``expansion_ratio``,
``lexical_density``, ``cognitive_load``, ``zipf_deviation``) is already
produced by :meth:`~core.services.experiment_runner.ExperimentRunner
._run_one`. **Adherence & metrics** -- heatmap plus
workload/latency/velocity/diversity/distance charts, including a "Real
generation speed (tokens/sec)" chart from Ollama's own per-call timing
alongside the older word-count-based ``ms_per_word`` proxy. **High-Dim
analytics** -- parallel-categories "logic pipeline" plots, productivity bar,
two scatter matrices. **Zipf deviation** -- distribution and by-archetype
charts over :meth:`~core.analysis.nlp_science.PsychScientist.zipf_deviation`.

Each chart checks its own required columns before rendering rather than
assuming a fixed field set -- found necessary after a real early export
(predating Stage 6's full field set) crashed the Adherence sub-tab
outright; it now renders whatever a sparse run's columns actually support
instead of 500ing on the first missing one.

Plotly.js is vendored locally under ``web/static/vendor/plotly/`` (no CDN
dependency, matching htmx). Charts deliberately use only the canonical
(NLTK-tokenized) ``word_count``/``ms_per_word`` fields, never the ``_raw``
naive-split ones Stage 6 preserved to avoid discarding data -- the two are
the same concept computed twice, not separate metrics worth charting both.

See :mod:`api.routers.analytics`, :mod:`web.plotting.analytics_charts`.

Deep NLP investigation (``tab_nlp``)
------------------------------------------

**Reachable now:** yes -- ``GET /nlp``.

Three sub-tabs of Plotly charts over one run's persisted responses, ported from the legacy
``tab_nlp``. Unlike Stage 8's analytics (built with a plain ``pandas.json_normalize``), this uses
:meth:`~core.analysis.data_contract.LabDataBridge.build_dataframe` -- the same data path the
legacy tab itself used, confirmed by reading it directly. **NLP-1** -- POS morphology ternary
plot, cognitive-complexity scatter (readability vs. vocabulary diversity), emotional-engagement
scatter (subjectivity vs. sentiment, faceted by bias). **NLP-2** -- emotional-stability box plot,
repetition-by-bias box plot. **NLP-3** -- sentence-length distribution, two self-focus-vs-rigidity
scatters, rigidity-by-bias box, abstraction-vs-cognitive-load scatter, narrative-coherence box,
emotional-volatility box.

Every chart's column is guaranteed present -- :class:`~core.analysis.data_contract.LabSchema`
gives every declared field a default -- so no Stage-8-style per-chart column guards were needed
here.

Real bug found and fixed before building on top of it: :meth:`~core.analysis.data_contract
.LabDataBridge.transform_raw`'s ``neuro_self_focus`` mapping read the bare ``"self_focus"`` key
unconditionally, silently grabbing ``PsychScientist``'s value instead of ``NeuroMetrics``'
(``self_focus_ext``) on every current entry -- the exact same collision story as Stage 6's own
``self_focus`` bug, replaying one layer downstream in a consumer that was never updated to match.
Fixed to prefer ``self_focus_ext``, with a fallback to the bare key for historical exports.

See :mod:`api.routers.nlp`, :mod:`web.plotting.nlp_charts`, :mod:`core.analysis.data_contract`.

Multi-dimensional analysis (``tab_clusters``)
---------------------------------------------------

**Reachable now:** yes -- ``GET /clusters``.

Three sub-tabs over one run's persisted responses, ported from the legacy ``tab_clusters`` -- the
largest remaining tab (``streamlit_app.py:1548-2856``). The legacy tab turned out to contain
**three overlapping implementations** of the same UMAP+HDBSCAN+confirmatory-fit-indices workflow,
confirmed by counting actual calls rather than skimming: ``UMAP()`` invoked 4 times, ``HDBSCAN()``
4 times, each fit-index function 3 times, all in one 1307-line tab. Only the most complete,
most-recently-iterated version -- "Behavioral topology" -- is ported; the other two ("HDBSCAN +
UMAP" and its "v.2") are confirmed duplicate scope creep, deliberately left behind, matching how
``data_contract_old.py`` was handled earlier in this migration.

**K-Means (PCA)** -- :class:`~core.analysis.cluster_discovery.ClusterDiscovery` (pre-existing),
split into business logic (``process_data()``) and presentation
(:func:`~web.plotting.cluster_charts.build_kmeans_pca_view`) per the plan's original design: PCA
scatter colored by archetype, PC1/PC2 axis-driver tables, cluster-purity table. **HDBSCAN
(Density)** -- :func:`~core.services.cluster_discovery.run_plain_hdbscan`, density clustering
directly on full-dimensional scaled features (no UMAP), genuinely distinct from the workflow below.
**Behavioral topology** -- :func:`~core.services.cluster_discovery.run_behavioral_topology`: filter
(validity, min word count, no raw JSON, min coherence) -> two independent UMAP embeddings (2D for
plotting, N-D for the actual clustering -- matching the legacy app's own deliberate split, since
forcing both onto one 2D projection distorts density) -> HDBSCAN on the N-D embedding ->
:func:`~core.services.cluster_discovery.compute_fit_indices` (CLAUDE.md SS3b's
silhouette/Davies-Bouldin/label-alignment-ARI construct-validity numbers). Seven sub-views: latent
projection, HDBSCAN topology (MST + condensed-tree, matplotlib), cluster membership tables,
research-mode correlation heatmap, behavioral anomalies, and the raw fit indices.

Four real bugs found and fixed purely by testing against small/edge-case data before ever reaching
live verification: (1) ``ClusterDiscovery.process_data`` raised instead of degrading gracefully
when rows < ``n_clusters``; (2) ``hdbscan``'s own ``condensed_tree_.plot()`` genuinely crashes on
small datasets -- the *legacy* app already wraps this in a bare ``try/except``, which had been
dropped during an early port and was restored to match; (3) ``run_behavioral_topology`` crashed
when filtering left zero rows; (4) UMAP itself crashes on too-few-rows relative to ``n_neighbors``,
fixed with one guard covering both (3) and (4): a workflow-wide minimum-rows threshold that
short-circuits to a clearly-labeled empty result instead of crashing.

Verified against real live Ollama data, not just synthetic fixtures: a genuine 1-record run
correctly shows "not enough data" on all three sub-tabs; a real 40-task run against a local
``mistral:7b-instruct-q4_K_M`` (5 archetypes x 8 temperature-sweep steps, ~51 seconds end to end)
produced 24 filtered responses -- enough to clear Behavioral topology's minimum-rows threshold --
and rendered the complete happy path: real Plotly scatters, real PC1/PC2 driver and purity tables,
a real condensed-tree PNG, and real fit indices (silhouette 0.251, Davies-Bouldin 0.675, ARI 0.040,
noise ratio 4.2% on 24 samples / 2 clusters / 18 features).

See :mod:`api.routers.clusters`, :mod:`core.services.cluster_discovery`,
:mod:`web.plotting.cluster_charts`, :mod:`core.analysis.cluster_discovery`.

Model evaluation (``tab_model_evo``)
---------------------------------------

**Reachable now:** yes -- ``GET /model_evo``.

Fits a baseline logistic-regression model
(:class:`~core.analysis.model_evaluation.ModelEvaluation`, a pre-existing, framework-agnostic
module -- no split needed, unlike Stage 10's ``ClusterDiscovery``) predicting a user-chosen discrete
column (e.g. ``archetype``, ``v_ok_numeric``) from a run's numeric metrics -- how well do the
linguistic/neuro metrics actually predict a label. A two-step htmx flow: the run picker swaps in a
target-column selector (candidates are columns with 2-10 unique values and a non-``float64`` dtype
-- the legacy tab's own heuristic, preserved exactly) and a test-size slider; submitting renders
precision/recall/F1/ROC-AUC, a confusion-matrix table + Plotly heatmap, the classification report,
and a feature-importance table + bar chart. Unlike Stages 7-10's pure read-only views, this one
runs real (cheap, local) computation per request -- but still read-only over already-persisted data.

Both of ``evaluate()``'s own ``ValueError``\ s (dataset under 10 rows, missing target column) render
as an inline message rather than a 5xx -- a normal, expected outcome of a user's column/test-size
choice against real data, the same "graceful degradation, not a crash" precedent Stage 8/10
established for insufficient data.

See :mod:`api.routers.model_evo`, :mod:`web.plotting.model_evo_charts`,
:mod:`core.analysis.model_evaluation`.

Benchmark report (``tab_benchmark``)
---------------------------------------

**Reachable now:** yes -- ``GET /benchmark``.

Read-only aggregation over one run's persisted responses -- dataset overview, pass-rate/latency
charts, a quality-metrics heatmap and psycholinguistic-signature chart (each guarded by the legacy
tab's own per-column existence check, since both are optional even on a fully-populated run), and a
weighted model leaderboard (40% success rate, 30% coherence, 30% inference speed -- a former 30%
"teacher-mimicry via ``semantic_overlap``" term was removed 2026-08-24, see
:doc:`wiki/04-llm-analytics`'s "A metric that contradicted itself" section: that field measures
similarity to the bias label, not to any teacher output, and was directly rewarding the same
high-similarity behavior the Layer 1 echo-detection cascade rejects) naming a "champion" model. Kept
as plain functions in
:mod:`web.plotting.benchmark_charts`, like Stage 8's analytics charts, rather than a separate
``core/services`` module -- pure pandas aggregation, nothing worth unit-pinning apart from the
charts themselves.

Guards for a sparse run missing required columns (student/teacher/output/word_count/v_ok/
ms_per_word/duration_ms) with a clear message instead of a 500 -- the same real-data finding Stage 8
made first, applied here before ever hitting it live.

See :mod:`api.routers.benchmark`, :mod:`web.plotting.benchmark_charts`.

Raw data / schema (scoped down from ``tab_monitor``/``tab_debug``)
--------------------------------------------------------------------------

**Reachable now:** yes -- ``GET /monitor``.

Column dtypes and the full response table -- every row, not just a preview -- over one run's
persisted responses; a "Show all N rows" toggle switches between a 20-row preview and the complete
table. The direct replacement for the legacy Streamlit app's ``st.dataframe(df_display, ...)`` full
data view, now reachable per-run rather than only inline with a live generation session. Deliberately
narrower than the legacy ``tab_monitor``/``tab_debug`` pair -- reading the actual legacy code before
building anything found a real mismatch with this project's own migration plan, which had assumed
``tab_monitor`` was schema introspection. It's actually Ollama *model management*: pulling a model
via ``subprocess.Popen(["ollama", "pull", ...])``, listing installed models, and deleting one via
``ollama.delete()`` -- a genuinely different risk profile (subprocess execution, a destructive
delete action) than anything else in this read-only analysis app. The schema/dtype table that *was*
intended actually lives in ``tab_debug`` (gated behind a ``SHOW_DEBUG_TAB`` flag), alongside an
unrelated raw dump of Streamlit's own session-state object -- a Streamlit-specific concept with no
equivalent in this stateless FastAPI app.

Flagged to the author rather than silently building the subprocess/destructive-delete surface, or
silently dropping the schema check; the author chose to port the schema/dtype inspector only. Ollama
model management and the session-state dump are left out entirely, not deferred -- documented as a
deliberate scope decision in :mod:`api.routers.monitor`'s own module docstring. The legacy
Arrow-compatibility coercion around the schema-check dataframe (worked around Streamlit's Arrow-based
table renderer) isn't ported either -- plain ``DataFrame.to_html()`` has no such requirement.

See :mod:`api.routers.monitor`.

FAQ (``tab_faq``)
---------------------

**Reachable now:** yes -- ``GET /faq``.

Serves ``faq_eng.md``/``faq_ua.md`` via a language toggle, matching the legacy tab exactly. The one
real implementation decision: Streamlit's ``st.markdown`` auto-renders markdown, which Jinja2 has no
equivalent for, so the page renders it via :class:`markdown_it.MarkdownIt` instead -- already an
existing transitive dependency (pulled in by ``myst-parser`` for the Sphinx build), now promoted to
a direct pin in ``requirements.in`` since the running app imports it at runtime, not just the
offline docs build.

See :mod:`api.routers.faq`.

Config-driven batch runner (``cli/``)
------------------------------------------

**Reachable now:** yes -- ``python -m cli.run_experiment --config path/to/experiment.toml``.

A second front end over the same :class:`~core.services.experiment_runner.ExperimentRunner` and
real adapters :mod:`api.routers.experiments` wires -- no FastAPI/SSE, no orchestration logic
duplicated. Since ``ExperimentRunner.try_start`` is asyncio-coupled by design (built for the SSE
use case: an ``asyncio.Queue`` fed from a background thread), the CLI wraps it in its own internal
``asyncio.run()`` rather than refactoring that already-tested class -- invisible to the person
running it from a terminal, who just sees one progress line printed per event, ending in
``Done -- N/N -- run <id>``.

Config files are **TOML** (``tomllib``, Python 3.12 standard library -- no new dependency), loaded
straight into :class:`~core.domain.entities.ExperimentConfig` via ``ExperimentConfig(**data)`` --
the entity is already a pydantic ``BaseModel`` whose own docstring anticipated this exact reuse, so
a malformed config gets pydantic's own validation errors, not a separate CLI-specific schema. See
``cli/example_config.toml`` for the full field reference.

Verified against real local Ollama: the produced JSONL has the *exact same 66 keys* as a real
web-generated run, and the run is fully readable by ``GET /runs/summary`` -- the CLI and web front
ends genuinely interoperate through the same ``Repository``, not just superficially matching shapes.

See :mod:`cli.run_experiment`.

Chart / visualization reference
------------------------------------

Every chart the app renders, grouped by the page and sub-tab it appears on, with the module
function that builds it -- pulled directly from ``web/plotting/*.py``'s real ``title=``/tuple-label
values, not reconstructed from memory. A few titles are dynamic (marked *dynamic*) -- the column
being plotted is chosen at request time (e.g. the K-Means color-by dimension), so the table shows
the template, not one fixed string. This table is source, not the legacy
``utils/plotly/plotly_parser.py`` AST auditor -- that script is Streamlit-``with``-tab-specific
(built for ``legacy/streamlit_app.py``'s tab structure) and doesn't parse this codebase's
``web/plotting/`` module layout at all, confirmed by reading it directly rather than assumed to
still apply after the rewrite.

.. list-table::
   :widths: 15 20 40 25
   :header-rows: 1

   * - Page
     - Sub-tab / section
     - Chart
     - Source
   * - ``/analytics``
     - Adherence & metrics
     - Adherence heatmap (by parameter)
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Workload distribution
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Latency (ms)
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Generation velocity (ms/word)
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Real generation speed (tokens/sec, from Ollama's own timing)
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Word count consistency
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Vocabulary diversity ratio
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Levenshtein distance to prompt/bias
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Semantic alignment overlap
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Psycholinguistic signature ("Style distribution (raw space)")
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Pass rate by prompt strategy
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - Adherence & metrics
     - Coherence stability by prompt strategy
     - :func:`~web.plotting.analytics_charts.build_adherence_charts`
   * - ``/analytics``
     - High-Dim analytics
     - Logic pipeline | Color: Archetype
     - :func:`~web.plotting.analytics_charts.build_high_dim_charts`
   * - ``/analytics``
     - High-Dim analytics
     - Logic pipeline | Color: v_ok (Success)
     - :func:`~web.plotting.analytics_charts.build_high_dim_charts`
   * - ``/analytics``
     - High-Dim analytics
     - Model productivity matrix
     - :func:`~web.plotting.analytics_charts.build_high_dim_charts`
   * - ``/analytics``
     - High-Dim analytics
     - Teacher impact matrix
     - :func:`~web.plotting.analytics_charts.build_high_dim_charts`
   * - ``/analytics``
     - High-Dim analytics
     - Cross-model dependency matrix
     - :func:`~web.plotting.analytics_charts.build_high_dim_charts`
   * - ``/analytics``
     - Zipf deviation
     - Zipf deviation distribution (normalized)
     - :func:`~web.plotting.analytics_charts.build_zipf_charts`
   * - ``/analytics``
     - Zipf deviation
     - Zipf deviation by archetype
     - :func:`~web.plotting.analytics_charts.build_zipf_charts`
   * - ``/nlp``
     - NLP-1
     - POS morphology profile
     - :func:`~web.plotting.nlp_charts.build_nlp1_charts`
   * - ``/nlp``
     - NLP-1
     - Cognitive complexity (readability vs. diversity)
     - :func:`~web.plotting.nlp_charts.build_nlp1_charts`
   * - ``/nlp``
     - NLP-1
     - Emotional engagement (subjectivity vs. sentiment)
     - :func:`~web.plotting.nlp_charts.build_nlp1_charts`
   * - ``/nlp``
     - NLP-2
     - Emotional stability (sentiment variance)
     - :func:`~web.plotting.nlp_charts.build_nlp2_charts`
   * - ``/nlp``
     - NLP-2
     - Repetition / fixation patterns
     - :func:`~web.plotting.nlp_charts.build_nlp2_charts`
   * - ``/nlp``
     - NLP-3
     - Syntactic flow (sentence length distribution)
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/nlp``
     - NLP-3
     - Self-focus vs. cognitive rigidity
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/nlp``
     - NLP-3
     - Self-focus vs. cognitive rigidity (bias dependency)
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/nlp``
     - NLP-3
     - Rigidity distribution by bias type
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/nlp``
     - NLP-3
     - Abstraction vs. cognitive load
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/nlp``
     - NLP-3
     - Narrative coherence distribution
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/nlp``
     - NLP-3
     - Emotional volatility (sentence variance)
     - :func:`~web.plotting.nlp_charts.build_nlp3_charts`
   * - ``/clusters``
     - K-Means (PCA)
     - *dynamic:* "PCA space: <color-by dimension> distribution"
     - :func:`~web.plotting.cluster_charts.build_kmeans_pca_view`
   * - ``/clusters``
     - K-Means (PCA)
     - *dynamic:* "Top drivers for <PC1/PC2>"
     - :func:`~web.plotting.cluster_charts.build_kmeans_pca_view`
   * - ``/clusters``
     - HDBSCAN (Density)
     - HDBSCAN: density-based groups
     - :func:`~web.plotting.cluster_charts.build_plain_hdbscan_view`
   * - ``/clusters``
     - Behavioral topology
     - UMAP projection space
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/clusters``
     - Behavioral topology
     - Behavioral topology scatter map
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/clusters``
     - Behavioral topology
     - Minimum spanning tree (matplotlib -- gracefully unavailable on some runs, see SS10's found-after-the-fact log)
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/clusters``
     - Behavioral topology
     - Condensed tree (matplotlib)
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/clusters``
     - Behavioral topology (research mode)
     - Feature correlation matrix
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/clusters``
     - Behavioral topology (research mode)
     - *dynamic:* "<feature X> vs. <feature Y> by cluster"
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/clusters``
     - Behavioral topology (anomalies)
     - Outliers by model
     - :func:`~web.plotting.cluster_charts.build_behavioral_topology_views`
   * - ``/model_evo``
     - --
     - Confusion matrix heatmap
     - :func:`~web.plotting.model_evo_charts.build_model_evo_view`
   * - ``/model_evo``
     - --
     - Feature importance
     - :func:`~web.plotting.model_evo_charts.build_model_evo_view`
   * - ``/benchmark``
     - --
     - Pass rate (%) by model (v_ok_numeric)
     - :func:`~web.plotting.benchmark_charts.build_benchmark_view`
   * - ``/benchmark``
     - --
     - Inference speed (Lower is better)
     - :func:`~web.plotting.benchmark_charts.build_benchmark_view`
   * - ``/benchmark``
     - --
     - Avg quality scores per model
     - :func:`~web.plotting.benchmark_charts.build_benchmark_view`
   * - ``/benchmark``
     - --
     - Linguistic trait distribution
     - :func:`~web.plotting.benchmark_charts.build_benchmark_view`

42 chart entries across 6 pages/13 sub-tabs (36 fixed-title Plotly charts, 2 matplotlib images, 2
dynamic-title Plotly charts each covering 2-3 concrete instances depending on user selection). The
weighted leaderboard table on ``/benchmark`` and the membership/purity/fit-index tables across
``/clusters`` are not included here -- they're real data tables, not charts, and are already
covered by each page's own description above.

Knowledge Graph (``/knowledge_graph``)
--------------------------------------------

Added 2026-09-05, promoted out of the legacy Neo4j subsystem (:doc:`../wiki/07-knowledge-graph-results`)
by explicit author decision -- a real `core.domain` interface
(:class:`~core.domain.interfaces.GraphRepository`) and adapter
(:class:`~core.adapters.neo4j_repo.Neo4jGraphRepo`), not a thin wrapper around the Streamlit tab.
Models the per-response cascade (Layer0/Layer1/Layer2/Judge) as an explicit lineage graph in Neo4j,
so root-cause analysis over the accumulated corpus is a graph traversal instead of a groupby someone
had to already think to write.

A "Sync failure-mode graph" action (per selected run) plus 3 real root-cause queries, corpus-wide
(every run ever synced, not scoped to one run): which model is most linked to Layer-1 echo
rejections; where the cascade chain actually terminates for one archetype; which RAG knowledge
categories precede echo rejections. Degrades to a clear inline error, not a 500, if Neo4j isn't
reachable -- no other page in this app depends on it.

**Deliberately not included here**: the original Archetype/Bias co-occurrence graph, the 4
PageRank scripts, Hypothesis Testing, and Uncertainty Analysis all remain on the separate
``streamlit run run_knowledge_graph.py`` entry point, untouched, per CLAUDE.md SS1 -- only the
failure-mode graph specifically was promoted into this app.

A 4th "structural analysis" query, added the same day: **Behavioral communities (Leiden)** --
Stage 4 of :doc:`../wiki/08-graph-representation-learning` graduating from design doc into real
code. Materializes a weighted co-occurrence relationship between Archetype/Bias/Model/
CascadeOutcome nodes (they only ever meet through a shared ``Response`` in the base schema), then
runs real Leiden community detection over that topology -- surfacing groupings nobody wrote a
query for in advance, unlike the 3 root-cause queries above. Reports GDS's own modularity score
alongside the results (real validation, not an eyeballed result) -- including honestly when that
number is unflattering.

A 5th query, same day: **Structural similarity (analogy / anomaly)** -- Stage 5 of the same roadmap.
Runs ``gds.fastRP.mutate`` + ``gds.knn.stream`` over the same co-occurrence graph to find the
strongest node-to-node analogies and the single most structurally anomalous node (the one whose
*closest* match is still weakest). On real synced data, this independently agreed with Stage 4's
Leiden communities -- two different algorithms landing on the same grouping, real convergent
evidence rather than a coincidence of one method.

Not yet built
----------------

.. note::
   This section previously said ``SQLiteRepo`` "exists and is tested but has no live endpoint" --
   true when written, resolved the same day: :mod:`api.routers.db_export` (**Export to DB** in the
   nav) now copies any run's JSONL data into it on demand via
   :func:`core.services.db_export.export_run_to_db`. Every response generated through the web UI or
   CLI still *lands* in ``JSONLStore`` by default -- SQLite is an opt-in copy, not the primary
   store -- but it's reachable now, not just built. See :doc:`operations`'s "Inspecting results
   directly" section for the real, verified walkthrough.

.. note::
   This section previously also listed Stage 16's cutover/consolidation (``streamlit_app.py``'s
   fate, retiring confirmed duplicates, final architecture-diagram regeneration) as remaining --
   stale since Stage 16 itself landed. That work is done: ``streamlit_app.py`` moved to
   ``legacy/streamlit_app.py`` via ``git mv``; the "confirmed duplicate" framing for
   ``streamlit_app_.py`` turned out to be wrong on inspection (a real diff shows 3013 changed lines
   and opposite Neo4j wiring, not a duplicate -- left untouched pending further author triage, not
   retired); and the ER/business-flow/class-relations diagrams were regenerated at Stage 16, with
   the feature-mindmap/clustering-pipeline/Neo4j-flow diagrams added afterward. See the refactor
   plan's Stage 16 entry and "found after the fact" log for the full record.
