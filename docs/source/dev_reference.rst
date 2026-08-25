Developer reference -- packages and modules
================================================

A map of what's on disk and what it's for, one level more concrete than :doc:`architecture`'s
diagrams -- this page names the actual packages and points at the auto-generated module pages for
full detail. If you're looking for "where does X live," start here.

Primary layout (the FastAPI rewrite -- Stages 0-16, see :doc:`roadmap`)
------------------------------------------------------------------------------

``api/`` -- FastAPI app and routers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``api/app.py`` -- the application factory, mounts ``/static``, wires every router, serves the
  landing page.
- ``api/_paths.py`` -- absolute ``TEMPLATES_DIR``/``STATIC_DIR``/``REPO_ROOT``, anchored to this
  module's own location rather than the process's working directory (matters for Sphinx, which
  imports these modules from ``docs/source/``, not the repo root).
- ``api/routers/`` -- one module per page: ``experiments`` (Stages 5-6), ``runs`` (7),
  ``analytics`` (8), ``nlp`` (9), ``clusters`` (10), ``model_evo`` (11), ``benchmark`` (12),
  ``monitor`` (13), ``faq`` (14), plus ``demo`` (Stage 1's throwaway SSE proof-of-concept, kept as
  a documented reference). Full listing: :doc:`api.routers`.

``web/`` -- templates and chart-building
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``web/templates/`` -- Jinja2 + HTMX. One full page per route (``experiments.html``,
  ``analytics.html``, ...) plus one ``_*.html`` fragment per htmx-swapped section.
- ``web/plotting/`` -- pure presentation, one module per tab (``analytics_charts.py``,
  ``nlp_charts.py``, ``cluster_charts.py``, ``benchmark_charts.py``, ``model_evo_charts.py``),
  plus shared helpers ``render.py`` (Plotly -> HTML div) and ``mpl_render.py`` (matplotlib -> base64
  PNG ``<img>``, used only where HDBSCAN's own MST/condensed-tree plots need it). Full listing:
  :doc:`web.plotting`.
- ``web/static/`` -- ``style.css`` (shared, minimal styling) and ``vendor/`` (htmx, Plotly.js,
  vendored locally -- no CDN dependency anywhere in this app).

``cli/`` -- headless batch runner (Stage 15)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``cli/run_experiment.py`` -- a second front end over the same ``ExperimentRunner`` and adapters the
web app uses; no FastAPI/SSE, config comes from a TOML file (``cli/example_config.toml``) instead
of a form. See :doc:`operations` for a full run-through.

``core/domain/`` -- entities and interfaces, zero framework imports
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``entities.py`` -- pydantic models: ``ExperimentConfig``, ``RunRecord``, ``GenerationResult``,
  ``JudgeVerdict``, ``PromptMode``.
- ``interfaces.py`` -- ``typing.Protocol`` definitions: ``LLMClient``, ``Judge``,
  ``PromptStrategy``, ``Repository``, ``KnowledgeBase``. Nothing here imports FastAPI, Streamlit,
  Ollama, or any concrete adapter -- that's the whole point of this layer (see :doc:`architecture`'s
  layering rule).

``core/services/`` -- orchestration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``experiment_runner.py`` -- ``ExperimentRunner``, the write-path orchestrator every front end
  (web, CLI) drives: builds prompts, generates, judges, computes metrics, persists, streams
  progress.
- ``metrics_engine.py`` -- ``MetricsEngine``, the read-side aggregation ``/runs`` uses.
- ``cluster_discovery.py`` -- ``run_plain_hdbscan``/``run_behavioral_topology``/
  ``compute_fit_indices``, the Stage 10 UMAP+HDBSCAN+confirmatory-fit-indices workflow.
- ``_sse.py`` -- the asyncio-queue bridge shared by the real SSE endpoint and (internally) by the
  CLI's own one-shot ``asyncio.run()`` wrapper.

``core/adapters/`` -- concrete implementations of the ``domain`` interfaces
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``ollama_client.py`` -- ``OllamaClient``, calls Ollama's native ``/api/chat`` (real token counts
  and timing breakdown, not just text).
- ``jsonl_store.py`` / ``sqlite_repo.py`` -- both implement ``Repository``; ``JSONLStore`` is the
  live backend, ``SQLiteRepo`` is built and tested but not wired to any endpoint (see
  :doc:`operations` for using it standalone).
- ``structured_judge.py`` -- ``StructuredJudge`` (2026-08-24, replaces the former ``naive_judge.py``
  / ``NaiveJudge``): genuinely parses the judge model's ``{verdict, confidence, rationale}`` JSON
  instead of substring-matching ``"true"``. CLAUDE.md SS4's author-swap boundary, now crossed by one
  narrow, explicit exception (CLAUDE.md SS6) -- the judge's own pass/fail *criteria* are still
  whatever the underlying LLM decides, not authored here.
- ``prompt_strategy.py`` -- ``NaivePromptStrategy``, the three system-prompt construction modes.
- ``rag/`` -- ``chunking.py``, ``ingestion.py`` (``RAGEngine``), ``retriever.py``,
  ``vector_store.py`` (FAISS), ``knowledge_base.py`` (the ``RAGKnowledgeBase`` adapter wrapping
  ``RAGEngine`` behind the ``KnowledgeBase`` interface).

``core/analysis/`` -- the metric-computation "moat" (CLAUDE.md SS1)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pre-existing, framework-agnostic modules, wired behind ``domain`` interfaces via
``ExperimentRunner`` rather than rewritten: ``nlp_science.py`` (``PsychScientist`` -- sentiment,
TTR, ARI, Zipf deviation, ...), ``neuro_metrics.py`` (``NeuroMetrics`` -- rigidity, cognitive load,
coherence, self-focus), ``calculate_advanced_linguistic_metrics.py`` (lexical density,
Levenshtein-to-prompt distance), ``data_contract.py`` (``LabSchema``/``LabDataBridge``, the
validated-schema data path ``/nlp`` uses), ``cluster_discovery.py`` (the original ``ClusterDiscovery``
KMeans+PCA class -- distinct from ``core/services/cluster_discovery.py``'s newer UMAP+HDBSCAN
workflow), ``model_evaluation.py`` (``ModelEvaluation``, the ``/model_evo`` baseline classifier).
``response_classification.py`` (new 2026-08-24) -- Layer 0 (``classify_response``, deterministic
validity gates) and Layer 1 (``is_echo_response``, embedding-based echo detection) of the
per-response cascade (CLAUDE.md SS3a), wired into ``ExperimentRunner._run_one`` ahead of the other
metrics and the judge call.

Legacy -- untouched by this rewrite (CLAUDE.md constraint 1)
------------------------------------------------------------------

- ``core/service/neo4j_service.py`` -- ``Neo4jService``, the py2neo client wrapper.
- ``core/tabs/knowledge_graph.py`` -- ``KnowledgeGraph``, the Neo4j sync/PageRank/visualization
  logic. See its own module docstring for a detailed "why this looks frozen" note.
- ``utils/other/neo4j_services.py`` -- free functions that launch the Neo4j server *process*.
- ``run_knowledge_graph.py`` (repo root) -- the small Stage 16 script that calls
  ``KnowledgeGraph.knowledge_graph_tab`` today; the only live Streamlit entry point.
- ``legacy/streamlit_app.py`` -- the original ~3,400-line monolith, moved here at Stage 16,
  reference-only.

Supporting
--------------

- ``utils/`` -- ``config_loader_short.py``/``config_loader_long.py`` (read ``config/config.ini``
  and ``config/config.toml``), ``app_utils.py``, plus author-facing dev scripts
  (``fake_data_generator/``, ``project_audit/``, ``list_tests.py`` -- this project's own
  test-roster generator, see :doc:`qa`) not wired into the app's own runtime logic.
- ``config/config.ini`` -- ``[neo4j]``, ``[rag]``, ``[OLLAMA]``, ``[DIRECTORIES]``, ``[FILES]``,
  ``[EXPERIMENT]`` sections. ``config/config.toml`` -- Streamlit server settings only.
  ``config/knowledge_base.json`` -- unused today, superseded by ``knowledge/rag/``'s directory of
  ``.txt`` files (see the ``DIRECTORIES``-vs-``FILES`` ``knowledge_path`` key collision noted in
  CLAUDE.md SS5 if you're tracing why).
- ``knowledge/rag/`` -- the RAG knowledge-base text files.
- ``tests/`` -- see :doc:`qa` for the full breakdown; ``conftest.py`` provides the session-scoped
  ``rag`` fixture every RAG test shares.
- ``results/`` -- ``lab_experiment_results/`` (real experiment output, the ``JSONLStore``
  directory), ``coverage_html/``, ``allure-results/``, ``pytest_test_results/`` -- all generated,
  none committed.

Full auto-generated module reference
------------------------------------------

Every public class/function's real docstring, one page per top-level package:
:doc:`api`, :doc:`cli`, :doc:`core`, :doc:`utils`, :doc:`web`.
