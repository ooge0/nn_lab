Migration Roadmap
===================

``nn_lab`` is being rebuilt from a single 3437-line Streamlit script into
the layered architecture described in :doc:`architecture`, one stage at a
time, each with its own tests verified before the next stage starts (see
CLAUDE.md's "one front at a time" discipline). This page is the
stage-by-stage record: what each stage built, why, and -- where relevant --
real bugs found in the legacy code along the way and *deliberately not*
carried forward. See :doc:`features` for what's actually usable today.

Ground rules this migration follows
--------------------------------------

- **Strictly single-user, single-session.** No multi-user isolation design;
  no Docker, no cloud -- plain ``uvicorn`` on bare metal.
- **The legacy Neo4j/knowledge-graph subsystem stays exactly as-is**,
  untouched, on its current code path. Not part of this migration at all --
  a separate future plan, after this one lands.
- **The author hand-writes the judge/cascade/confirmatory-validation
  logic** -- the project's "moat" -- once scaffolding proves out. Stages
  wire the *existing* naive validator behaviour (bug included) behind a
  clean interface so the app stays functional end-to-end; the real judge
  drops in later without any upstream caller needing to change.
- **Ollama only, for now.** No paid backend is wired in.

Stages
---------

Stage 0 -- Scaffolding, dependency baseline, config split, docs wiring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Empty target packages (``core/domain``, ``core/services``, ``core/adapters``,
``api``, ``web``, ``cli``); ``fastapi``/``sqlalchemy`` added as direct
dependencies; Sphinx wired to autodoc and PlantUML from day one, including
this documentation set.

*Found and fixed along the way:* ``requirements.in`` pinned two mutually
incompatible Sphinx versions (`pip-compile` couldn't resolve at all).
``requirements-base.txt`` pinned an exact ``torch`` version that doesn't
exist on the CUDA wheel index the README's own install instructions use --
meaning a fresh install following the documented steps would silently
replace a working GPU build with a CPU-only one. Both fixed at the
dependency-pin level, not worked around locally.

Stage 1 -- SSE + background-thread live-progress mechanism
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

The riskiest, most novel piece of the whole rewrite, proven first and in
isolation, before any real generation logic depends on it: a background
thread streams progress to the browser via Server-Sent Events, replacing
Streamlit's rerun-based UI model entirely. See :doc:`features` for the
live demo and :mod:`core.services._demo_runner` for the mechanism.

*Found and fixed along the way:* the background thread threw an unhandled
exception when the owning event loop closed mid-run (the real-world
Ctrl+C-during-a-run case) -- now caught and logged instead of crashing
noisily.

Stage 2 -- Domain interfaces
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

``LLMClient``, ``Judge``, ``PromptStrategy``, ``KnowledgeBase``,
``Repository`` -- defined as runtime-checkable ``Protocol`` classes, zero
framework imports, each shaped directly from the real legacy call it
replaces (not designed in the abstract). See :mod:`core.domain.interfaces`.

Stage 3 -- Adapters
~~~~~~~~~~~~~~~~~~~~~~

**Status: done** (``OpenAIClient`` dropped from scope -- Ollama-only for now, no paid backend).

Concrete implementations of the Stage 2 interfaces: :class:`~core.adapters
.ollama_client.OllamaClient` (verified against a real running Ollama
server, not just mocks), two interchangeable :class:`~core.domain
.interfaces.Repository` implementations
(:class:`~core.adapters.jsonl_store.JSONLStore`,
:class:`~core.adapters.sqlite_repo.SQLiteRepo`), the RAG module relocated
from ``core/rag/`` to ``core/adapters/rag/`` (with every import across the
still-live legacy app updated so nothing broke), and
:class:`~core.adapters.prompt_strategy.NaivePromptStrategy`.

*Found and fixed along the way:* the legacy "Exclude archetype from
prompt" checkbox only ever affected the UI preview text -- it was never
read by the real generation code, so it silently did nothing in the live
app. Not carried forward: the new adapter's equivalent parameter actually
works. Separately, the legacy "Save JSONL" pattern buffers every response
in memory and only writes to disk on a manual button click -- a crash
loses everything; the new ``JSONLStore`` appends per response instead,
since a headless background-thread run has no button to click in the
first place.

Stage 4 -- Naive judge (the author-swap boundary)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

:class:`~core.adapters.naive_judge.NaiveJudge` reproduces the legacy
validator's exact pass/fail decision, bug included: it asks for structured
JSON but then checks ``"true" in text.lower()`` instead of parsing it, so
a malformed response is silently indistinguishable from a genuine "no".
Confirmed via a manual line-by-line diff against the legacy call. This is
deliberate -- the point of this stage is a clean call site for the
author's real judge to replace later, not a fix.

*Found along the way:* the Stage 2 ``Judge`` interface had no way to vary
the judge model per call, which self-critic mode requires (the judge model
changes depending on which student was just evaluated). Fixed before
building on it.

.. note::
   **2026-08-24 update:** this author-swap boundary was crossed. Following a direct code review by
   the author (four specific defects raised: the fake ``semantic_overlap`` field, the unnormalized
   ``cognitive_load`` average, and this stage's own known judge bug, plus a request for a QA page),
   the author granted the AI agent one narrow, explicit exception to CLAUDE.md SS6's "author writes
   the moat" rule -- not a general lifting of the boundary. ``NaiveJudge`` was replaced by
   :class:`~core.adapters.structured_judge.StructuredJudge`, which genuinely parses the judge's JSON
   response instead of substring-matching ``"true"``. What did **not** change: the judge's own
   pass/fail *criteria* are untouched (still whatever the underlying LLM decides), and cascade
   Layer 2 (NLI/toxicity classifiers) remains unbuilt, still the author's to write. See
   :doc:`wiki/04-llm-analytics` for the full story, including a real Layer 1 threshold-inversion
   finding from calibrating against this project's own data, and CLAUDE.md SS4 for the exact,
   permanent record of what changed and why.

Stage 5 -- ``ExperimentRunner`` core loop (generation-only)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

First real-logic vertical slice: one student model, one archetype, no
judge/sweep/RAG/self-critic yet (Stage 6). Replaces Stage 1's throwaway
demo runner with the real thing, reusing the same proven SSE mechanism
(and its thread/event-loop bridging helper, extracted into a shared
module rather than duplicated). Verified end to end against a real local
Ollama server across multiple models -- including catching a genuine
weak-model failure mode live (a small model echoing the prompt's own
placeholder template instead of generating real content), independent
confirmation of the same pattern Stage 0's real-data analysis had already
flagged from a sampled export.

*Found and fixed along the way:* an early version of the error-handling
path would have silently swallowed a real generation failure (e.g. Ollama
connection refused) as if it were the unrelated "event loop closed
mid-run" case, both being plain ``RuntimeError`` -- caught by a test
before it shipped, fixed by narrowing exactly which call the "loop
closed" handling wraps. Separately, ``api/app.py``'s static-file mount and
both routers' template directories used bare relative paths
(``"web/static"``), which only resolve correctly if the process's working
directory happens to be the repo root -- true for `uvicorn` run from
there, but not for Sphinx importing the module from ``docs/source/``,
which is exactly how it was caught. Fixed with absolute paths anchored to
the module's own location, centralized in one shared module instead of
computed separately (and inconsistently) in three files.

Stage 6 -- Full ``tab_gen`` parity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Extends Stage 5 to match the legacy generation tab exactly: judge routing
(self-critic vs. teacher/student), prompt mode selection, parameter sweep
(Delta/MIN-MAX resolved server-side to a concrete range, linear
interpolation pinned against the legacy formula), RAG toggle (lazily
loaded on first use), split-biases. Deliberately single-dynamic-parameter
sweep only, matching the legacy radio-button constraint -- see the "Not
part of this migration" reasoning in the project's planning discussion:
true multi-parameter grid search multiplies runtime by a second `steps`
factor with no cluster to absorb it. A hard cap on total_tasks
(``config.ini``'s ``[EXPERIMENT] max_total_tasks``) refuses an oversized
run outright rather than just previewing it. Verified end to end against
real Ollama, including self-critic routing and a live temperature sweep.

*Found and fixed along the way:* a genuine, silent data-loss bug --
``self_focus`` is computed independently by two metric modules with
different pronoun sets, and ``word_count``/``ms_per_word`` independently
by two more with different tokenization, all under the *same* key names.
The legacy dict-merge lets whichever computation runs last silently
overwrite the other; confirmed on real text losing the more accurate
value in favour of a wrong ``0.0``. Fixed at the merge point by renaming
the losing side, matching a naming convention (``_ext`` suffix) the
codebase already uses for its other overlapping fields but had missed
applying to this one. Separately, mypy caught two real correctness gaps
introduced while wiring the sweep and judge routing -- a sweep declared
without a resolved value range, and a missing ``teacher_model`` when
self-critic is off -- both now rejected with a clear error before any
generation starts, instead of failing deep inside the loop.

Stage 7 -- ``tab_perf``: read-only run summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

The first purely read-side vertical slice, over data Stage 6 already
produces: :class:`~core.services.metrics_engine.MetricsEngine` aggregates
one run's persisted responses (record/step counts, sweep range, timing
averages, teacher/student/archetype/bias/RAG summaries) exactly as the
legacy ``tab_perf``'s ``summary_data`` table does, reachable via
``GET /runs`` (a run picker) and ``GET /runs/summary`` (the htmx-swapped
summary fragment). Verified against real Ollama-generated runs end to end,
including a 2-record run to exercise the aggregation across multiple
archetypes.

*Found and fixed along the way:* a genuine prerequisite gap surfaced by
being the first real read-side consumer -- ``Repository`` had no way to
list which runs exist, and ``JSONLStore.save_run`` never actually
persisted a run's metadata anywhere retrievable (only an in-memory file
path). Fixed by adding ``Repository.list_runs()`` to the Stage 2 interface
and, for ``JSONLStore``, a ``<run>.meta.json`` sidecar file written
immediately on ``save_run`` (kept separate from the response ``.jsonl``
file so its row shape stays exactly the legacy per-response format, with
nothing for existing consumers to skip); ``SQLiteRepo`` already stored run
metadata properly in its ``runs`` table and only needed the query added.
Separately, the legacy "Steps" display has its own bug (shows a
sweep-configuration widget value instead of the data it computed and threw
away) -- not carried forward, since this engine only ever sees persisted
data, not live widget state. A first draft of ``total_steps`` then
introduced a *different* bug, caught only by the real-Ollama manual check
(the pinned unit-test fixture had used a fake integer): the persisted
``step`` field is actually a legacy-matching ``"N/total"`` string, and
``max()`` over such strings compares lexicographically, not numerically.
Fixed to match the legacy semantic exactly -- the last response's own
``step`` value, not a computed max. Also found (unrelated to this stage's
code): a stale Oracle "javapath" ``java.exe`` shim earlier on this dev
machine's ``PATH`` than the real working JDK silently broke the
PlantUML-diagram build step (exit 127, no output). Fixed by having
``conf.py`` resolve ``java`` via ``JAVA_HOME`` first, which is unaffected
by ``PATH`` ordering and works identically on Windows and Ubuntu.

Stage 8 -- ``tab_analytics`` (heatmap / high-dim / zipf)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Ports ``streamlit_app.py:1182-1357`` (three sub-tabs). Confirmed by reading
``ExperimentRunner._run_one`` directly, not assumed, before building
anything: every field every chart needs -- ``v_ok_numeric``, ``duration_ms``,
``word_count``, ``ms_per_word``, ``unique_ratio``, ``levenshtein_dist``,
``semantic_overlap``, ``punc_density``, ``expansion_ratio``,
``lexical_density``, ``cognitive_load``, ``zipf_deviation``, plus the
run/sweep/model/archetype fields -- is already computed and persisted by
Stage 6. This stage is pure visualization over existing data, not new
metric computation; the three sub-tabs are Adherence & metrics (heatmap,
workload/latency/velocity/diversity/distance charts), High-Dim analytics
(parallel-categories "logic pipeline" plots, productivity bar, two scatter
matrices -- ported fresh into :mod:`web.plotting.analytics_charts` from
``tmp/simple_plotty_staff.py``'s ``get_high_dim_dashboard``, which stays
untouched since the still-live legacy app still calls it directly), and
Zipf deviation (distribution + by-archetype charts over
:meth:`~core.analysis.nlp_science.PsychScientist.zipf_deviation`, Stage 3).
Plotly.js is vendored locally (``web/static/vendor/plotly/plotly.min.js``,
~4.6MB, extracted from the already-installed ``plotly`` package), matching
the htmx precedent -- no CDN dependency anywhere in the app.

**Locked decision:** charts use only the canonical (NLTK-tokenized)
``word_count``/``ms_per_word`` Stage 6 kept under those key names, never
the ``_raw`` (naive-``.split()``) fields the same fix preserved to avoid
silently discarding data. The two are the same concept computed two ways,
not two metrics worth visualizing separately -- resulting chart numbers may
differ slightly from legacy ``streamlit_app.py``'s (whose own key-collision
bug meant it was actually displaying the naive-split values under those
names), which is expected, not a regression to chase.

*Found and fixed along the way:* manual verification against a second real
run on disk -- an early export predating Stage 6, with only 5 fields
(``student``, ``archetype``, ``bias``, ``duration_ms``, ``output``; no
``teacher``, no ``val``, none of the metric fields) -- crashed the
Adherence sub-tab with a genuine 500. The chart-building code had assumed
every field is always present (mirroring the legacy Streamlit code, which
never guarded most of these charts either and would have crashed
identically on the same data); real disk data proved that assumption false
for anything generated before Stage 6 existed. Fixed by making each chart
check its own required columns independently rather than gating the whole
sub-tab on all-or-nothing -- the sparse run now renders the 2 of 9 charts
its columns actually support instead of failing outright, locked in with a
regression test using the exact field set that broke it.

Real Ollama performance telemetry (cross-stage, after Stage 8)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Author-requested addition, not a numbered stage: real per-response
performance data from Ollama, to "analyze model productivity" beyond the
existing word-count/wall-clock proxy. Investigated before writing code:
querying a live Ollama server via both its OpenAI-compatible endpoint (what
:class:`~core.adapters.ollama_client.OllamaClient` used) and its native
``/api/chat`` API showed the compat endpoint returns only basic token
counts -- none of Ollama's timing breakdown. Switched the adapter to
Ollama's native API (the official ``ollama`` package, already a
dependency, previously only used by the legacy app's model-management
calls) to get both: real ``prompt_tokens``/``completion_tokens`` and a
``total_duration``/``load_duration``/``prompt_eval_duration``/
``eval_duration`` breakdown, all added as new *optional*
:class:`~core.domain.entities.GenerationResult` fields so every existing
fake/test double kept working unchanged. :class:`~core.services
.experiment_runner.ExperimentRunner` derives a real ``tokens_per_second``
from these; Stage 8's Adherence sub-tab gained a chart for it, alongside
(not replacing) the older ``ms_per_word`` proxy. The naive judge stays on
the OpenAI-compatible endpoint, unchanged -- this is about the student
model's performance, not the judge's.

Verified against a real end-to-end run through the live server: the
resulting entry's real numbers surfaced a genuine, useful diagnostic on the
spot -- 4.4 of a 6.6-second total response was model *load* time, not
generation (which ran at a healthy 69 tokens/sec) -- exactly the kind of
load-vs-inference distinction the old wall-clock-only number couldn't show.

Stage 9 -- ``tab_nlp`` (3 sub-tabs)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Ports ``streamlit_app.py:1357-1541`` -- presentation-only over Stage 3's already-ported metrics
(:class:`~core.analysis.nlp_science.PsychScientist`, :class:`~core.analysis.neuro_metrics
.NeuroMetrics`, :mod:`core.analysis.calculate_advanced_linguistic_metrics`). Unlike Stage 8's
``tab_analytics`` (built with a plain ``pandas.json_normalize`` over raw responses), the legacy
``tab_nlp`` builds its DataFrame via :meth:`~core.analysis.data_contract.LabDataBridge
.build_dataframe` -- confirmed by reading the legacy code directly, a genuine difference between
what the two legacy tabs actually did, not an inconsistency introduced here. Twelve charts across
three sub-tabs (POS morphology, cognitive complexity, emotional engagement; emotional stability,
repetition/fixation; sentence structure, self-focus/rigidity, abstraction/cognitive load,
coherence). Every chart's column is guaranteed present -- :class:`~core.analysis.data_contract
.LabSchema` gives every declared field a default -- so no Stage-8-style per-chart guards were
needed here.

*Found and fixed along the way:* a real, live bug, caught before building anything on top of it.
:meth:`~core.analysis.data_contract.LabDataBridge.transform_raw`'s ``neuro_self_focus`` mapping
read the bare ``"self_focus"`` key unconditionally -- on real, current entries this silently
grabbed ``PsychScientist``'s value instead of ``NeuroMetrics``' (``self_focus_ext``), the exact
same story as Stage 6's own ``self_focus`` collision bug, replaying one layer downstream:
``neuro_metrics.py`` already suffixes six of its seven overlapping fields with ``_ext``, and
Stage 6's fix applied the same convention to ``self_focus`` at the merge point -- but
``LabDataBridge``, written against the *old* entry shape, was never updated to match. The existing
pinned test didn't catch this: its fixture's nested sub-dict had no ``self_focus``-ish key at all,
so both the buggy and fixed code hit the same default by coincidence. Fixed to prefer
``self_focus_ext``, falling back to the bare key for historical pre-Stage-6 exports -- mirroring
the identical extended-over-base pattern already used one line above for ``sentiment_variance``.
Verified directly against a real live-generated run, not just the fixture.

Stage 10 -- ``tab_clusters`` (PCA / HDBSCAN / UMAP, heaviest tab)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Ports ``streamlit_app.py:1548-2856``, the largest remaining tab. Before writing anything, counted
actual calls in the legacy code rather than skimming it: ``UMAP()`` is invoked 4 times,
``HDBSCAN()`` 4 times, each of the three fit-index functions 3 times, all within one 1307-line tab
-- the legacy tab has **three overlapping implementations** of the same
UMAP+HDBSCAN+confirmatory-fit-indices workflow ("HDBSCAN + UMAP", "HDBSCAN + UMAP v.2", and
"Behavioral topology"'s own sub-tabs). Confirmed with the author before porting anything: only
"Behavioral topology" (the most complete, most recently-iterated version -- feature-group
selection, real data filtering, 7 organized sub-views) is ported; the other two are confirmed
duplicate scope creep, deliberately left behind -- matching how ``data_contract_old.py`` was
handled earlier in this migration.

Three sub-tabs shipped: **K-Means (PCA)** (:class:`~core.analysis.cluster_discovery.ClusterDiscovery`,
pre-existing, split into ``process_data()`` business logic vs. :func:`~web.plotting.cluster_charts
.build_kmeans_pca_view` presentation, per the plan's original split), **HDBSCAN (Density)**
(:func:`~core.services.cluster_discovery.run_plain_hdbscan`, clusters on full-dimensional scaled
features directly, no UMAP), and **Behavioral topology**
(:func:`~core.services.cluster_discovery.run_behavioral_topology`, the ported workflow: filter -->
two separate UMAP embeddings -- 2D for visualization, N-D for the actual clustering, matching the
legacy app's own deliberate split, since forcing both onto one 2D projection distorts density -->
HDBSCAN on the N-D embedding --> :func:`~core.services.cluster_discovery.compute_fit_indices`,
CLAUDE.md SS3b's silhouette/Davies-Bouldin/ARI confirmatory-validation numbers). First use of
matplotlib in this rewrite (:mod:`web.plotting.mpl_render`, ``Agg`` backend, figure-to-base64-PNG),
needed for HDBSCAN's own MST/condensed-tree plots.

*Four real bugs found and fixed, all via testing against small/edge-case data before ever reaching
live verification, none hypothetical:*

1. **``ClusterDiscovery.process_data`` crashed when rows < ``n_clusters``** -- ``KMeans(n_clusters=3)
   .fit_predict()`` raised ``ValueError`` instead of degrading like the module's own pre-existing
   empty-columns guard. This is in the pre-existing, previously-untested ``core/analysis
   /cluster_discovery.py`` -- fixed since real endpoint wiring exercised it for the first time.
2. **``condensed_tree_.plot()`` crash** -- ``hdbscan``'s own matplotlib rendering threw
   ``ValueError: setting an array element with a sequence`` on a small synthetic dataset. The
   *legacy* app already anticipates this exact failure with a bare ``try/except`` around both
   MST and condensed-tree plotting -- dropped during an early port, restored to match legacy
   exactly, with a comment noting it's a real reproducible failure mode.
3. **``run_behavioral_topology`` crashed on 0 rows surviving filtering** -- ``StandardScaler
   .fit_transform()`` raised on an empty array when every response was filtered out (e.g. all
   shorter than ``min_words``).
4. **UMAP crashed on too-few-rows relative to ``n_neighbors``** -- even after fixing (3), a
   2-row case still failed inside UMAP itself. Fixed with one guard covering both cases:
   ``min_rows_needed = max(min_cluster_size, vis_neighbors, cluster_neighbors) + 1`` --  below that,
   the workflow short-circuits to an empty, clearly-labeled result instead of crashing.

*Router-side follow-on bug:* after adding guard (4), the router's own check for whether to build the
Behavioral topology view (``len(bt_result.df) > 0``) was checking the wrong condition -- the
short-circuited result's ``df`` is non-empty (the filtered-but-unprocessed input) but lacks the
``x_vis``/``y_vis`` columns the view needs. Fixed by checking ``"x_vis" in bt_result.df.columns``
instead of a length check.

Every sub-tab guards for too-little-data with a clear message rather than a 500 (``{% if kmeans
%}...{% else %}<p>Not enough data points...`` -- matching the per-chart-guard pattern Stage 8
established).

**Representative files:** :mod:`core.analysis.cluster_discovery` (bug fix only, business logic left
in place), :mod:`core.services.cluster_discovery` (new), :mod:`web.plotting.mpl_render` (new),
:mod:`web.plotting.cluster_charts` (new), :mod:`api.routers.clusters`,
``web/templates/clusters.html``, ``web/templates/_clusters_charts.html``.

**Verification:** unit tests -- done, ``tests/unit/test_cluster_discovery.py`` (17 tests: pinned exact
values for :func:`~core.services.cluster_discovery.compute_fit_indices` on a fixed synthetic
embedding since it's pure deterministic math; structural tests for the UMAP/HDBSCAN-driven
functions, since exact cluster-ID assignment isn't stable across library versions/platforms even
with a fixed seed; regression tests for all four bugs above); functional API tests -- done,
``tests/integration/test_clusters_api.py`` (4 tests: empty state, unknown run, graceful degradation, full
happy-path against 25 synthetic responses). Manual verification against **real live Ollama data**,
not just synthetic fixtures: confirmed graceful degradation against a genuine 1-record run (all
three sub-tabs correctly show their "not enough data" message); then, since no existing real run
had enough records to exercise the full happy path, started a real 40-task experiment against a
live local ``mistral:7b-instruct-q4_K_M`` (5 archetypes x 8 temperature-sweep steps, completed in
51 seconds) -- 24 of the 40 responses survived Behavioral topology's filters, clearing its 21-row
minimum threshold. The resulting ``/clusters/charts`` response rendered the complete happy path for
real: K-Means scatter + PC1/PC2 driver tables + purity table, HDBSCAN density scatter (8/25 noise on
an earlier smaller run), and all 7 Behavioral-topology sub-views -- latent projection, HDBSCAN
topology (condensed-tree rendered as a real base64 PNG; MST gracefully unavailable via bug (2)'s
fix), cluster membership tables, research-mode correlation heatmap, behavioral-anomalies table,
and real fit indices (24 samples, 2 clusters, 18 features, silhouette 0.251, Davies-Bouldin 0.675,
ARI 0.040, noise ratio 4.2%) -- 9 real Plotly chart divs and 1 real matplotlib image, zero "not
enough data" messages.

Stage 11 -- ``tab_model_evo``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Ports ``streamlit_app.py:2856-3022`` -- fits a baseline logistic-regression model
(:class:`~core.analysis.model_evaluation.ModelEvaluation`, a pre-existing, framework-agnostic
module -- no split needed, unlike Stage 10's ``ClusterDiscovery``) predicting a user-chosen discrete
column (e.g. ``archetype``, ``v_ok_numeric``) from a run's numeric metrics. Unlike Stages 7-10's
pure read-only views, this one runs real (cheap, local) computation per request, but it's still
read-only over already-persisted data. A two-step htmx flow: the run picker swaps in a
target-column selector (the same "2-10 unique values, not float64" heuristic the legacy tab used,
preserved exactly) and a test-size slider; submitting that form POSTs to ``/model_evo/evaluate``,
which renders precision/recall/F1/ROC-AUC, a confusion-matrix table + Plotly heatmap, the
classification report, and a feature-importance table + bar chart.

Both of :meth:`~core.analysis.model_evaluation.ModelEvaluation.evaluate`'s own ``ValueError``\
s (too few rows, missing target column) are caught and rendered as an inline message rather than a
5xx -- a normal, expected outcome of a user's column/test-size choice against real data, the same
"graceful degradation, not a crash" precedent Stage 8/10 established for insufficient data.

**Representative files:** :mod:`api.routers.model_evo`, :mod:`web.plotting.model_evo_charts`,
``web/templates/model_evo.html``, ``web/templates/_model_evo_targets.html``,
``web/templates/_model_evo_results.html``.

**Verification:** functional API tests -- done, ``tests/integration/test_model_evo_api.py`` (7 tests: empty
state, target-column listing, a real fit against a synthetic 3-class classifiable dataset, the
too-few-rows and missing-target-column error paths, unknown-run 404). Manual check against a real
40-response Ollama run (``mistral:7b-instruct-q4_K_M``) -- fitting on ``archetype`` produced a real
precision/ROC-AUC of 0.933 and 2 real Plotly chart divs.

Stage 12 -- ``tab_benchmark``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Ports ``streamlit_app.py:3026-3178`` -- read-only aggregation over one run's persisted responses
(dataset overview, pass-rate/latency/quality-heatmap/psycholinguistic charts, and a weighted model
leaderboard), the same pattern as Stage 7's ``MetricsEngine``. Kept as plain functions in
:mod:`web.plotting.benchmark_charts` rather than a separate ``core/services`` module, like Stage 8 --
straightforward pandas aggregation with no algorithm worth unit-pinning apart from the charts
themselves. Guards for a sparse/pre-Stage-5 run missing required columns
(student/teacher/output/word_count/v_ok/ms_per_word/duration_ms) with a clear message instead of a
500, mirroring Stage 8's own real-data finding; the quality-heatmap and psycholinguistic-signature
charts additionally use the legacy tab's own per-column existence guards (``existing_quality``/
``existing_psy``) since those are optional even on a fully-populated run.

**Representative files:** :mod:`api.routers.benchmark`, :mod:`web.plotting.benchmark_charts`,
``web/templates/benchmark.html``, ``web/templates/_benchmark_report.html``.

**Verification:** functional API tests -- done, ``tests/integration/test_benchmark_api.py`` (4 tests: empty
state, a populated run with an overview/leaderboard/champion, unknown-run 404, graceful degradation
on a sparse fixture). Manual check against the real 40-response mistral run: 40 total / 35 valid
samples, 4 real Plotly chart divs, correct champion identification.

Stage 13 -- Schema check (scoped down from ``tab_monitor``/``tab_debug``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done (partial scope -- confirmed with the author).**

Reading the actual legacy code before building anything surfaced a real mismatch with this plan's
own original description ("tab_monitor + tab_debug... schema/dtype inspection... low-risk
introspection view"). What's actually there: ``tab_monitor`` (``streamlit_app.py:3189-3387``) is
Ollama *model management* -- pulling a model via ``subprocess.Popen(["ollama", "pull", ...])``,
listing installed models, and deleting one via ``ollama.delete()`` -- a genuinely different risk
profile (subprocess execution, a destructive delete action) than anything else in this read-only
analysis app. ``tab_debug`` (``streamlit_app.py:3391-3415``, gated behind a ``SHOW_DEBUG_TAB``
flag) is two unrelated things: a raw dump of Streamlit's own session-state object via
``st.json(st.session_state.to_dict())`` -- a Streamlit-specific concept with no equivalent in this
stateless FastAPI app -- and a schema/dtype table, which *is* the low-risk introspection view the
plan originally intended.

Flagged to the author rather than silently building the subprocess/destructive-delete surface or
silently dropping the schema check; author chose to port the schema/dtype inspector only. Ollama
model management and the session-state dump are left out entirely, not deferred as a TODO --
documented in :mod:`api.routers.monitor`'s own module docstring so the omission reads as a
deliberate scope decision. The legacy Arrow-compatibility coercion around the schema-check
dataframe (``fillna``/``astype(object)`` per column, worked around Streamlit's Arrow-based table
renderer) isn't ported either -- a rendering-engine workaround, not a ``Repository``-data concern;
plain ``DataFrame.to_html()`` has no such requirement.

**Representative files:** :mod:`api.routers.monitor`, ``web/templates/monitor.html``,
``web/templates/_monitor_schema.html``.

**Verification:** functional API tests -- done, ``tests/integration/test_monitor_api.py`` (4 tests: empty
state, correct dtype/row/column counts and names for a fixture, unknown-run 404, a real preview
table with real cell values). Manual check against the real 40-response mistral run: reports 40
rows x 69 columns, both the dtypes table and the data-preview table render with real content.

Stage 14 -- ``tab_faq``
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Trivial, matching the plan's own description exactly: ``streamlit_app.py:3420-3437`` serves
``faq_eng.md``/``faq_ua.md`` via a language toggle. The one real implementation decision: Streamlit's
``st.markdown`` auto-renders markdown, which Jinja2 has no equivalent for, so the page renders it
via :class:`markdown_it.MarkdownIt` -- already an existing transitive dependency (pulled in by
``myst-parser`` for the Sphinx build) now promoted to a direct pin in ``requirements.in`` since the
running app imports it at runtime, not just the offline docs build (see the found-after-the-fact
log for the ``requirements-base.txt`` staleness this surfaced).

**Representative files:** :mod:`api.routers.faq`, ``web/templates/faq.html``.

**Verification:** functional API tests -- done, ``tests/integration/test_faq_api.py`` (4 tests: English
default, a genuinely different Ukrainian render, an unknown-language inline error instead of a
crash, both language links present). Manual check: both ``/faq`` and ``/faq?lang=Українська``
render real file content (21.6KB / 31.1KB of HTML respectively) against the actual repo files.

Stage 15 -- ``cli/`` batch runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Was missing entirely from the project before this stage. Reuses
:class:`~core.services.experiment_runner.ExperimentRunner` and the same real adapters
:mod:`api.routers.experiments` wires -- one orchestration class, two front ends, zero duplicated
logic. ``ExperimentRunner.try_start`` is asyncio-coupled by design (an ``asyncio.Queue`` + a
background thread, built for the SSE use case); rather than refactoring that already-tested class
for a second calling convention, :func:`~cli.run_experiment.run` wraps it in its own internal
``asyncio.run()`` -- invisible to the person running it from a terminal -- and prints one line per
event drained from the same queue ``/experiments/stream`` reads from.

Config file format is **TOML**, not YAML -- Python 3.12 (this project's required version) ships
``tomllib`` in the standard library, and ``config/config.toml`` already establishes TOML as this
project's own config format, so no new dependency (``pyyaml``) was needed.
:func:`~cli.run_experiment.load_config` loads a TOML file straight into
:class:`~core.domain.entities.ExperimentConfig` (``ExperimentConfig(**data)``) rather than adding a
separate CLI-specific schema -- the entity is already a pydantic ``BaseModel`` whose own docstring
anticipated this exact reuse, so pydantic's own validation applies for free. ``sweep_min``/
``sweep_max`` in a config file are the already-resolved endpoints (matching the entity's own
contract), not the web UI's Delta/MIN-MAX input modes.

**Real bug found and fixed before shipping:** ``run()``'s ``out: TextIO = sys.stdout`` default
argument bound the *module-import-time* ``sys.stdout`` object rather than the current one at call
time -- invisible in production (both are the same real terminal stdout) but caught immediately by
``main()``'s own end-to-end test, where ``pytest``'s ``capsys`` redirection silently didn't apply to
the stale bound reference. Fixed by resolving ``out`` inside the function body instead of as a
default-argument value.

**Representative files:** :mod:`cli.run_experiment`, ``cli/example_config.toml``.

**Verification:** unit tests -- done, ``tests/unit/test_cli_run_experiment.py`` (6 tests: TOML parsing,
a missing-required-field rejection, progress/Done output with every response reaching a fake
repository, an invalid-config rejection before any generation starts, an already-running guard, and
a full ``main()`` end-to-end run against a real temp config file). Manual check -- done, ``python -m
cli.run_experiment --config cli/example_config.toml`` against real local Ollama: clean progress
output ending in ``Done -- 2/2 -- run ...``, and the produced JSONL has the *exact same 66 keys* as
a real web-generated run (zero CLI-only or web-only keys) -- confirmed identical, not just similar.
``GET /runs/summary`` against the CLI-generated run id returned 200 with the correct record count,
confirming the CLI and web front ends genuinely interoperate through the same ``Repository``.

Stage 16 -- Cutover and consolidation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status: done.**

Four decisions this stage's plan text flagged as the author's to make, not to resolve silently --
investigated first, then presented as concrete options rather than the plan's own (partly stale)
assumptions:

- **``streamlit_app.py``'s fate:** author chose to extract ``tab_knowledge_graph`` into a small new
  standalone script rather than keep the full monolith runnable. ``run_knowledge_graph.py`` (repo
  root) now does this -- loads a run via ``JSONLStore`` (the same one the FastAPI app and CLI use,
  so any run from either front end is reachable), then calls the existing, untouched
  ``KnowledgeGraph.knowledge_graph_tab(df)``. ``streamlit_app.py`` itself moved to
  ``legacy/streamlit_app.py`` via ``git mv`` (history and the author's own pending uncommitted
  edits both preserved, nothing discarded).
- **``streamlit_app_.py``:** investigated before asking -- turned out **not** to be the
  "undifferentiated duplicate" the plan's own text (and CLAUDE.md SS12) assumed. A real diff shows
  3013 changed lines and opposite Neo4j wiring, it's untracked in git (unlike every other
  ``streamlit_app*.py``), and it imports ``core.tabs.failure_taxonomy`` -- a module already deleted
  -- so it cannot currently run. Author chose to leave it untouched and investigate further before
  deciding its fate, rather than accept the plan's original "retire it" framing on stale evidence.
- **``streamlit_app_lang_localization.py``:** confirmed genuinely distinct (2566 diff lines),
  git-tracked, with its own pending uncommitted edits, and actively kept in sync with real
  refactors -- its RAG import was deliberately updated during Stage 3's ``core/rag/`` ->
  ``core/adapters/rag/`` move, alongside ``streamlit_app.py``. Author deferred a decision; left
  untouched.
- **``test_data/`` vs ``results/``:** a full-repo grep confirmed zero test or code references
  ``test_data/`` anywhere -- despite the name, it's not wired as a fixture source for anything;
  ``results/lab_experiment_results/`` (read via ``JSONLStore``) is the only tree the app actually
  uses. Two files are byte-identical duplicates between the trees. Author's explicit choice: leave
  both trees exactly as they are -- a known, accepted state, not an unresolved question.

**Documentation consolidation** (CLAUDE.md SS8): the architecture page gained three new diagrams
generated from the real, finished code -- an entity-relationship diagram (``JSONLStore``'s two
files vs. ``SQLiteRepo``'s two real tables, both serializing the same logical
``RunRecord``/response-dict pair), a two-part business-flow activity diagram (the write-path
per-response cascade and the read-path corpus-level confirmatory analysis, matching CLAUDE.md
SS3a/SS3b exactly, traced through the real classes), and a class-relations diagram (every
``core.domain`` entity/interface and which adapter satisfies each). The existing component diagram
was also fixed: it still referenced the already-removed ``OpenAIClient`` (Stage 3) and was missing
five routers (``model_evo``/``benchmark``/``monitor``/``faq``/``clusters``) and
``core/services/cluster_discovery.py``. README.MD was fully restructured into CLAUDE.md SS8's
mandated order (Core app -> Services -> Architecture -> Tests -> API Reference) -- the old version
was a 27-heading, un-thematic grab-bag mixing current content with confirmed-fictional material
(a "TOX Commands Cheat Sheet" documenting ``lint``/``format``/``type``/``coverage``/``streamlit``/
``eval``/``rag``/``llm`` tox environments that don't exist in ``tox.ini``, and a "Phase 2" pointing
at a ``run.bat``/``Makefile`` that don't exist on disk either -- both cut, not carried forward).
CLAUDE.md itself updated: SS12's "pre-rewrite legacy layout" framing replaced with the actual
current layout (Stages 0-15 built and primary), SS1/SS5's Neo4j bullets corrected, the
``failure_taxonomy``/``test_data``/``streamlit_app_.py`` findings folded in.

**Representative files:** ``run_knowledge_graph.py`` (new), ``legacy/streamlit_app.py`` (moved via
``git mv``), ``docs/source/architecture.rst`` (3 new diagrams + component-diagram fixes),
``README.MD`` (full restructure), ``CLAUDE.md`` (SS1/SS2/SS5/SS11/SS12 updated), ``docs/source/index.rst``.

**Verification:** clean Sphinx rebuild (``-E -W --keep-going``) stays at the stable 9-warning
baseline with all 5 architecture diagrams rendering as real images (spot-checked visually, not just
"no error" -- the ER diagram and write-path activity diagram both confirmed to show the intended
content); full ``pytest tests -v`` unaffected (no code changed, only docs/file locations); manual
check -- ``legacy/streamlit_app.py``'s size (149310 bytes) and line count (3437) confirmed identical
before/after the ``git mv``, nothing lost.

Not part of this migration
------------------------------

``tab_knowledge_graph`` stays wired to its current Neo4j code path
(``core/service/neo4j_service.py``, ``utils/other/neo4j_services.py``,
``core/tabs/knowledge_graph.py``) exactly as it is today, untouched --
revisited only as a separate future plan after this one lands.
