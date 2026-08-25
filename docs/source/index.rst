nn_lab documentation
======================

``nn_lab`` (Psycho-Data-Augmentor) is a portfolio project built to demonstrate one specific skill:
testing large language models rigorously, not just using them. It generates synthetic text by
conditioning local LLMs (via `Ollama <https://ollama.com>`_, no paid API) on behavioral archetypes,
then runs a validation and linguistic/statistical analysis pipeline over the resulting corpus to
check whether the generated text actually reflects the archetype it was asked to produce -- and
whether the metrics used to measure that are themselves trustworthy, not just noise dressed up as
signal.

It started as a single ~3,400-line Streamlit script and was rebuilt, stage by stage (Stages 0-15,
see :doc:`roadmap`), into the layered FastAPI application described in :doc:`architecture`. As of
Stage 16, that rewrite is the primary way to run the app -- the original script now lives at
``legacy/streamlit_app.py`` (kept for reference, superseded everywhere except
``tab_knowledge_graph``, extracted into its own small standalone script,
``run_knowledge_graph.py`` -- see *UI layers* below). The rebuild itself is part of what's being
demonstrated -- staged, tested, documented software engineering, not a one-shot script. It is not a
product and isn't meant to scale past one user on one machine.

UI layers
------------

Two separate UIs currently run side by side -- the new one doesn't replace the old one yet (see
:doc:`roadmap` for what's ported so far, :doc:`features` for what's reachable today).

**New (FastAPI + Jinja2 + HTMX)** -- start with ``uvicorn api.app:app --reload``, then open:

.. list-table::
   :widths: 25 30 45
   :header-rows: 1

   * - Page
     - URL
     - What
   * - Landing page
     - http://127.0.0.1:8000/
     - Links to every page below
   * - Run an experiment
     - http://127.0.0.1:8000/experiments
     - Full ``tab_gen`` parity -- judge, sweep, RAG, self-critic
   * - Run summaries
     - http://127.0.0.1:8000/runs
     - ``tab_perf`` -- record counts, timing, model/archetype/bias breakdown
   * - Analytics
     - http://127.0.0.1:8000/analytics
     - ``tab_analytics`` -- adherence, high-dim, Zipf-deviation, real-tokens/sec charts
   * - ↳ Adherence & metrics
     - http://127.0.0.1:8000/analytics#adherence
     - Heatmap, workload, latency, velocity, diversity, distance, real tokens/sec
   * - ↳ High-Dim analytics
     - http://127.0.0.1:8000/analytics#high-dim
     - Logic-pipeline, productivity, teacher-impact/cross-model matrices
   * - ↳ Zipf deviation
     - http://127.0.0.1:8000/analytics#zipf
     - Distribution + by-archetype charts
   * - Deep NLP investigation
     - http://127.0.0.1:8000/nlp
     - ``tab_nlp`` -- POS morphology, cognitive/emotional, neuropsychological charts
   * - ↳ NLP-1
     - http://127.0.0.1:8000/nlp#nlp-1
     - POS morphology, cognitive complexity, emotional engagement
   * - ↳ NLP-2
     - http://127.0.0.1:8000/nlp#nlp-2
     - Emotional stability, repetition/fixation
   * - ↳ NLP-3
     - http://127.0.0.1:8000/nlp#nlp-3
     - Sentence structure, neuropsychological metrics, coherence
   * - Multi-dimensional analysis
     - http://127.0.0.1:8000/clusters
     - ``tab_clusters`` -- K-Means, HDBSCAN, Behavioral topology
   * - ↳ K-Means (PCA)
     - http://127.0.0.1:8000/clusters#kmeans-pca
     - PCA scatter, PC1/PC2 axis drivers, cluster-purity table
   * - ↳ HDBSCAN (Density)
     - http://127.0.0.1:8000/clusters#hdbscan-density
     - Density-based clustering on full-dimensional scaled features
   * - ↳ Behavioral topology
     - http://127.0.0.1:8000/clusters#behavioral-topology
     - UMAP+HDBSCAN projection, membership, research mode, anomalies, fit indices
   * - Model evaluation
     - http://127.0.0.1:8000/model_evo
     - ``tab_model_evo`` -- baseline logistic-regression fit predicting a chosen label
   * - Benchmark
     - http://127.0.0.1:8000/benchmark
     - ``tab_benchmark`` -- overview, pass-rate/quality charts, weighted leaderboard
   * - Raw data / schema
     - http://127.0.0.1:8000/monitor
     - Scoped from ``tab_monitor``/``tab_debug`` -- every response as a real table, plus column dtypes
   * - Export to DB
     - http://127.0.0.1:8000/db_export
     - Copy any run's JSONL data into ``results/nn_lab.db`` (``SQLiteRepo``) on demand -- pick a run, click Send to DB
   * - FAQ
     - http://127.0.0.1:8000/faq
     - ``tab_faq`` -- user guide and metric methodology (English / Українська)
   * - API docs (Swagger)
     - http://127.0.0.1:8000/docs
     - Auto-generated, interactive, from the routers
   * - API docs (ReDoc)
     - http://127.0.0.1:8000/redoc
     - Same schema, read-only long-scroll format

Anchor links (``#adherence``, ``#nlp-1``, ``#kmeans-pca``, etc.) only resolve once a run with data
is selected -- the sub-tab headings they point to are part of the server-rendered chart content,
not present in the empty state.

**Legacy (Streamlit, Neo4j knowledge graph only)** -- start with ``streamlit run
run_knowledge_graph.py``, opens at http://localhost:8501 by default. The only remaining reason to
run Streamlit: ``tab_knowledge_graph`` stays on its Neo4j code path (CLAUDE.md constraint 1),
extracted into this small standalone script (Stage 16) rather than the full original monolith.
Loads a run's persisted responses via the same ``JSONLStore`` the FastAPI app and CLI both use, so
any run generated through either front end is reachable here too. The full original script is
still on disk at ``legacy/streamlit_app.py`` (and still technically runnable) but is kept purely
for reference -- every other tab it has now has a tested FastAPI/CLI equivalent.

**CLI (headless batch runner, Stage 15)** -- a third way to run an experiment, no browser needed::

    python -m cli.run_experiment --config cli/example_config.toml

Reuses the same ``ExperimentRunner`` and real adapters (``OllamaClient``, ``JSONLStore``,
``NaivePromptStrategy``, ``StructuredJudge``) as ``/experiments`` -- a config-driven TOML file in,
progress printed to stdout, an identical-shaped JSONL out. See ``cli/example_config.toml`` for the
full field reference (mirrors :class:`~core.domain.entities.ExperimentConfig` exactly).

.. toctree::
   :maxdepth: 3
   :caption: Contents:

   architecture
   wiki/index
   features
   operations
   qa
   glossary
   dev_reference
   roadmap
   modules
   core
   utils
   tests
   ../interface_and_components_v2_eng.md
   ../interface_and_components_v2_ua.md
   ../faq_eng.md
   ../faq_ua.md
