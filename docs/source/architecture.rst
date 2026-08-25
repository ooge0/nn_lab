Architecture
============

High-level component diagram
-----------------------------

Two front ends (the web UI and the CLI batch runner) both drive one
``ExperimentRunner``/``MetricsEngine`` service layer, which only ever talks to
``core.domain`` interfaces -- never directly to Ollama, SQLite, or JSONL
files. The legacy Neo4j/knowledge-graph subsystem is drawn deliberately
disconnected: it stays on its own existing code path (now reached via the
small standalone ``run_knowledge_graph.py`` script, Stage 16) and is not part
of this layered rewrite.

As of Stage 16 this is no longer just a *target* -- every box below has a
real implementation behind it and is the primary way to run the app (see
:doc:`roadmap`).

.. uml::

   @startuml
   skinparam componentStyle rectangle
   skinparam backgroundColor transparent
   skinparam shadowing false

   package "Front ends" {
     [web/\nJinja2 + HTMX] as WEB
     [cli/\nconfig-driven batch runner] as CLI
   }

   package "api/  (FastAPI)" {
     [Routers\n(experiments, runs, analytics, nlp, clusters,\nmodel_evo, benchmark, monitor, faq)] as ROUTERS
     [SSE endpoint\n(EventSourceResponse)] as SSE
   }

   package "core.services/  (orchestration)" {
     [ExperimentRunner] as RUNNER
     [MetricsEngine] as METRICS
     [cluster_discovery] as CLUSTERSVC
   }

   package "core.domain/  (interfaces + entities, zero framework imports)" {
     interface LLMClient as ILLM
     interface Judge as IJUDGE
     interface PromptStrategy as IPROMPT
     interface Repository as IREPO
     interface KnowledgeBase as IKB
   }

   package "core.adapters/  (concrete implementations)" {
     [OllamaClient] as AOLLAMA
     [JSONLStore] as AJSONL
     [SQLiteRepo] as ASQLITE
     [RAG adapters\n(FAISS + SentenceTransformers)] as ARAG
     [StructuredJudge\n(2026-08-24 author-directed swap)] as AJUDGE
     [NaivePromptStrategy] as APROMPT
   }

   package "External systems" {
     database Ollama as OLLAMA
     database SQLite as SQLITE
     database "JSONL files" as JSONL
     database "knowledge/rag/*.txt" as KB
   }

   package "Untouched legacy  (not part of this rewrite)" #FFDDDD {
     [run_knowledge_graph.py] as KGSCRIPT
     database Neo4j as NEO4J
   }

   WEB --> ROUTERS
   WEB ..> SSE : SSE
   CLI --> RUNNER
   ROUTERS --> RUNNER
   ROUTERS --> METRICS
   ROUTERS --> CLUSTERSVC
   SSE ..> RUNNER : progress events
   RUNNER --> ILLM
   RUNNER --> IJUDGE
   RUNNER --> IPROMPT
   RUNNER --> IREPO
   RUNNER --> IKB
   METRICS --> IREPO
   CLUSTERSVC --> IREPO

   ILLM ..|> AOLLAMA
   IJUDGE ..|> AJUDGE
   IPROMPT ..|> APROMPT
   IREPO ..|> AJSONL
   IREPO ..|> ASQLITE
   IKB ..|> ARAG

   AOLLAMA --> OLLAMA
   AJSONL --> JSONL
   ASQLITE --> SQLITE
   ARAG --> KB

   KGSCRIPT ..> AJSONL : reads runs via
   KGSCRIPT --> NEO4J
   @enduml

Entity-relationship diagram
------------------------------

One run has many responses, on both storage backends -- generated directly
from the real schemas, not idealized. ``JSONLStore`` (the live backend) keeps
this as two files per run rather than a database; ``SQLiteRepo`` (built and
tested, not yet wired to any endpoint -- see :doc:`features`) keeps it as two
real tables with a foreign key. Both sides serialize the *same* logical
records: :class:`~core.domain.entities.RunRecord` (run-level metadata) and
one persisted-response dict per generation call (the full 66-key schema
documented in :doc:`features`).

.. uml::

   @startuml
   skinparam backgroundColor transparent
   skinparam shadowing false

   package "JSONLStore (live backend)" {
     entity "<run_id>.meta.json" as META {
       * run_id : str <<PK>>
       --
       started_at : str
       total_tasks : int
       config : ExperimentConfig (nested JSON)
     }
     entity "lab_export_<run_id>.jsonl" as JSONL_FILE {
       * one line per response
       --
       run_id : str <<FK>>
       .. 66 fields total, see Features page ..
       student, teacher, archetype, bias, output
       v_ok, v_ok_numeric, duration_ms
       prompt_tokens, completion_tokens, tokens_per_second
       rag_enabled, rag_query, rag_chunks_count
       .. + every PsychScientist/NeuroMetrics/linguistic-metric field
     }
   }

   package "SQLiteRepo (built, tested, not yet wired to an endpoint)" {
     entity "runs" as RUNS {
       * run_id : str <<PK>>
       --
       started_at : str
       total_tasks : int
       config_json : JSON
     }
     entity "responses" as RESPONSES {
       * id : int <<PK, autoincrement>>
       --
       run_id : str <<FK -> runs.run_id>>
       data_json : JSON
     }
   }

   META ||--o{ JSONL_FILE : "run_id"
   RUNS ||--o{ RESPONSES : "run_id"
   @enduml

Business-flow diagram
------------------------

The two evaluation stages CLAUDE.md SS3 requires stay separate: the
per-response cascade (write path, ``ExperimentRunner``) never does
corpus-level work, and the confirmatory-analysis stage (read path,
Stage 8-12's routers) only ever runs over an already-persisted corpus. These
two activity diagrams trace one real request through each path.

Write path -- per-response cascade (CLAUDE.md SS3a)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. uml::

   @startuml
   skinparam backgroundColor transparent
   skinparam shadowing false

   start
   :Config in\n(web form / CLI TOML) -> ExperimentConfig;
   :ExperimentRunner.try_start\n(validate, concurrent-run guard,\nmax_total_tasks cap);
   if (rejected?) then (yes)
     :400 / 413 / "already running";
     stop
   endif
   :RunRecord persisted (Repository.save_run);

   partition "Per-response cascade (CLAUDE.md SS3a) -- for each\nstudent x archetype x bias x swept-value" {
     :PromptStrategy.build\n(+ KnowledgeBase.retrieve if RAG-enabled);
     :LLMClient.generate (OllamaClient);
     :extract_best_text;
     :Layer 0 -- classify_response\n(VALID / EMPTY / MALFORMED_JSON /\nTRUNCATED / SCHEMA_ERROR);
     if (Layer 0: VALID?) then (no)
       :minimal entry\n(metrics + judge both skipped);
     else (yes)
       :PsychScientist / NeuroMetrics /\ncalculate_advanced_linguistic_metrics\n(incl. Layer 1's semantic_overlap);
       if (Layer 1 -- is_echo_response\n(semantic_overlap > 0.5)?) then (yes, echo)
         :synthesize rejection JudgeVerdict\n(real judge call skipped);
         note right: Threshold is inverted from standard STS\nintuition -- rejects HIGH similarity to the\nbias label (echoed instruction), not low.\nCalibrated against real generated data,\nnot assumed. See wiki/04-llm-analytics.
       else (no, genuine)
         :Judge.evaluate (StructuredJudge);
       endif
     endif
     :entry dict assembled (66+ fields, incl.\nlayer0_classification / layer1_echo_detected);
     :Repository.save_response;
     :progress event -> SSE queue / CLI stdout;
   }
   note right: Layer 2 (NLI/sentiment/toxicity classifiers, CLAUDE.md SS3a)\nremains unbuilt -- the one cascade layer still\nreserved for the author to hand-write (CLAUDE.md SS6).

   :Run complete -> "done" event;
   stop

   @enduml

Read path -- corpus-level confirmatory analysis (CLAUDE.md SS3b)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. uml::

   @startuml
   skinparam backgroundColor transparent
   skinparam shadowing false

   start
   :GET /analytics, /nlp, /clusters,\n/model_evo, /benchmark, /monitor;
   :Repository.load_responses(run_id);
   if (no persisted responses?) then (yes)
     :404 "No responses found";
     stop
   endif
   :pandas.json_normalize\n(or LabDataBridge.build_dataframe for /nlp);

   partition "Corpus-level confirmatory analysis (CLAUDE.md SS3b) -- over\nthe WHOLE accumulated corpus, not one response" {
     :linguistic/NLP metric matrix\n(already computed per response, read back);
     :UMAP dimensionality reduction\n(/clusters -- Behavioral topology only);
     :HDBSCAN clustering;
     :Silhouette / Davies-Bouldin / ARI\n(compute_fit_indices);
     :Plotly / matplotlib rendering;
   }

   :200 -- rendered charts/tables;
   stop
   @enduml

Class-relations diagram
--------------------------

The domain layer's actual classes -- entities (pydantic models, plain data)
and interfaces (``Protocol``\ s, structurally satisfied, not inherited) --
and which concrete adapter satisfies each interface today.

.. uml::

   @startuml
   skinparam backgroundColor transparent
   skinparam shadowing false

   package "core.domain.entities (pydantic BaseModel)" {
     class ExperimentConfig {
       student_models: list[str]
       teacher_model: str | None
       self_critic: bool
       archetypes: list[str]
       biases: list[str]
       prompt_mode: PromptMode
       sweep_param/min/max/steps
       base_temperature/top_p/...
     }
     class RunRecord {
       run_id: str
       started_at: str
       config: ExperimentConfig
       total_tasks: int
     }
     class GenerationResult {
       text: str
       duration_ms: float
       model: str
       prompt_tokens/completion_tokens: int | None
       ollama_*_duration_ms: float | None
     }
     class JudgeVerdict {
       verdict: bool
       confidence: float | None
       rationale: str | None
     }
     enum PromptMode {
       TUNED
       BLIND
       RAW
     }
   }

   package "core.domain.interfaces (typing.Protocol)" {
     interface LLMClient {
       + generate(model, system_prompt, user_prompt, **params) : GenerationResult
     }
     interface Judge {
       + evaluate(response_text, archetype, bias, model) : JudgeVerdict
     }
     interface PromptStrategy {
       + build(archetype, bias, mode, **kwargs) : str
     }
     interface Repository {
       + save_run(run: RunRecord) : str
       + save_response(run_id, response: dict) : None
       + load_responses(run_id) : list[dict]
       + list_runs() : list[RunRecord]
     }
     interface KnowledgeBase {
       + retrieve(query, top_k) : list[dict]
     }
   }

   package "core.adapters (concrete, structurally satisfy the Protocols above)" {
     class OllamaClient
     class StructuredJudge
     class NaivePromptStrategy
     class JSONLStore
     class SQLiteRepo
     class RAGKnowledgeBase
   }

   RunRecord *-- ExperimentConfig : contains
   LLMClient <.. OllamaClient
   Judge <.. StructuredJudge
   PromptStrategy <.. NaivePromptStrategy
   Repository <.. JSONLStore
   Repository <.. SQLiteRepo
   KnowledgeBase <.. RAGKnowledgeBase

   OllamaClient ..> GenerationResult : returns
   StructuredJudge ..> JudgeVerdict : returns
   JSONLStore ..> RunRecord : persists/returns
   SQLiteRepo ..> RunRecord : persists/returns
   @enduml

Layering rule
-------------

``web`` / ``api`` depend on ``core.services``, which depends only on
``core.domain``. ``core.adapters`` implements ``core.domain`` interfaces;
``core.domain`` never imports from ``core.adapters``, ``api``, or ``web``.

Feature map (user journey)
------------------------------

Added 2026-08-24 at the author's request for a more navigable, "what can I actually do here"
overview, complementing the component/class/ER diagrams above (which answer "how is it built," not
"what does it do"). Every branch below is a real, reachable page or a real sub-capability of one --
traced directly against ``web/templates/_nav.html`` and each router, not invented for the
diagram. Colors group the same three CLAUDE.md SS3a/SS3b-derived categories the sidebar itself uses
(``[req]``/``[corpus]``/``[sys]``), plus a fourth for the per-response cascade specifically, since
it's a cross-cutting concept, not one page.

.. uml::

   @startmindmap
   * nn_lab
   left side
   **[#2c5f8a] Generation /experiments
   ***[#2c5f8a] Archetype x Bias conditioning
   ***[#2c5f8a] Prompt mode: Tuned / Blind / Raw
   ***[#2c5f8a] Parameter sweep
   ****[#2c5f8a] Temperature / Top-P
   ****[#2c5f8a] Frequency / Presence penalty
   ***[#2c5f8a] RAG toggle
   ****[#2c5f8a] Archetype+Bias / Archetype-only / Global
   ***[#2c5f8a] Self-critic vs. teacher-student
   ***[#2c5f8a] Live SSE progress + Stop button
   **[#8a4a2c] Per-response cascade
   ***[#8a4a2c] Layer 0 -- validity gate
   ***[#8a4a2c] Layer 1 -- echo detector
   ***[#8a4a2c] Layer 2 -- NLI vs. RAG context (logging-only)
   ***[#8a4a2c] Layer 3 -- StructuredJudge
   **[#2c5f8a] Performance /runs
   ***[#2c5f8a] Run summaries
   **[#2c5f8a] Model Evaluation /model_evo
   ***[#2c5f8a] Logistic-regression baseline
   ***[#2c5f8a] Feature importance
   right side
   **[#3a7d5c] Analytics /analytics
   ***[#3a7d5c] Adherence & metrics
   ***[#3a7d5c] High-Dim analytics
   ***[#3a7d5c] Zipf deviation
   **[#3a7d5c] NLP Science /nlp
   ***[#3a7d5c] NLP-1: morphology / cognition
   ***[#3a7d5c] NLP-2: emotional stability
   ***[#3a7d5c] NLP-3: self-focus / rigidity
   **[#3a7d5c] Clustering /clusters
   ***[#3a7d5c] KMeans + PCA
   ***[#3a7d5c] HDBSCAN (density)
   ***[#3a7d5c] Behavioral topology (UMAP)
   **[#3a7d5c] Benchmark /benchmark
   ***[#3a7d5c] Weighted leaderboard
   **[#6b6b6b] System Monitor /monitor
   ***[#6b6b6b] Schema / dtype inspector
   **[#6b6b6b] Service status
   ***[#6b6b6b] Ollama / NLTK / spaCy
   **[#6b6b6b] FAQ /faq
   @endmindmap

Tag cloud
------------

Generated by ``utils/generate_tag_cloud.py`` (run manually, output committed -- matches
``utils/list_tests.py``'s existing convention, not a Sphinx build-time step) from two real, cited
sources: every term name in :doc:`glossary`, and every real Python module under ``core``/``api``/
``web``. Word size is real occurrence frequency across ``docs/source/**/*.rst``, not an assumed
importance ranking -- a concept the docs actually discuss often renders larger than one mentioned in
passing, the same "measure it, don't assume it" discipline the rest of this project's docs follow.

.. image:: _static/tag_cloud.png
   :alt: Tag cloud of glossary terms and module names, sized by real occurrence frequency across the docs
   :width: 100%

Corpus-level analysis pipeline (clustering)
------------------------------------------------

The full path from a run's raw JSONL responses to the "Behavioral topology" view's rendered charts
(:func:`core.services.cluster_discovery.run_behavioral_topology`) -- the single heaviest computation
in the corpus-level confirmatory-analysis stage (CLAUDE.md SS3b).

.. uml::

   @startuml
   skinparam backgroundColor transparent
   skinparam shadowing false
   skinparam activity {
     BackgroundColor #f5f0ff
     BorderColor #6b4fa0
   }
   skinparam activityDiamond {
     BackgroundColor #eee6ff
     BorderColor #6b4fa0
   }

   start
   :Raw JSONL responses\n(Repository.load_responses);
   :Filter -- v_ok, min_words,\nJSON-echo removal, min_coherence;
   if (enough rows survive?\n(< min_cluster_size/vis_neighbors/\ncluster_neighbors + 1)) then (no)
     :empty BehavioralTopologyResult\n("not enough data" in the UI);
     stop
   endif
   :Select feature-group columns\n(Behavioral / Linguistic / Runtime / Validation);
   :StandardScaler.fit_transform;

   fork
     :UMAP -- 2D projection\n(x_vis, y_vis, for the scatter plot);
   fork again
     :UMAP -- 10-30D projection\n(a *separate* embedding, only for clustering --\nforcing both roles onto one 2D space distorts density);
   end fork

   :HDBSCAN.fit_predict\n(on the higher-D embedding);
   :cluster_id / cluster_name\nassigned (-1 = "Noise");

   fork
     :Outliers table\n(cluster_id == -1 rows);
   fork again
     :compute_fit_indices\n(Silhouette, Davies-Bouldin, ARI vs. archetype);
   fork again
     :MST / condensed-tree plots;
     note right: Both wrapped in try/except -- HDBSCAN's own\nplotting code can throw on small/degenerate inputs;\nfalls back to "unavailable" rather than a 500.
   end fork

   :Plotly (scatter, membership) +\nmatplotlib (condensed tree) rendering;
   :200 -- 7 Behavioral Topology sub-views;
   stop
   @enduml

Neo4j knowledge-graph flow (untouched legacy, CLAUDE.md SS1)
-------------------------------------------------------------------

Included for completeness, not as part of the layered rewrite -- this traces
``run_knowledge_graph.py`` -> :class:`~core.tabs.knowledge_graph.KnowledgeGraph`, exactly as they
exist on disk today. Per CLAUDE.md SS1 this subsystem is locked: no logic here has been touched,
adapted, or re-layered -- this diagram documents existing, unchanged behavior (the one standing
exception CLAUDE.md SS1 already carves out for "docstring/comment clarifications that add
historical or architectural context without changing behavior").

.. uml::

   @startuml
   skinparam backgroundColor transparent
   skinparam shadowing false
   skinparam activity {
     BackgroundColor #fdf0e8
     BorderColor #b5651d
   }

   start
   :run_knowledge_graph.py\n(standalone Streamlit entry point);
   :JSONLStore.load_responses(run_id)\n(same Repository the FastAPI app/CLI write to);
   :pandas DataFrame;
   :KnowledgeGraph.knowledge_graph_tab(df);

   partition "Neo4jService (py2neo)" {
     :load_neo4j_creds\n(config/config.ini [neo4j]);
     :Graph(uri, auth=(user, password));
   }

   if ("Sync history to Neo4j" clicked?) then (yes)
     :UNWIND $rows AS row\nMERGE (a:Archetype) MERGE (b:Bias)\nMERGE (a)-[:ASSOCIATED_WITH]->(b);
   endif

   partition "PageRank scripts (GDS)" {
     :CALL gds.graph.project\n(archetypeGraph / experimentGraph);
     :CALL gds.pageRank.stream;
     note right: Script-3's graph projection has a real,\ndisclosed unresolved bug -- "no procedure\ngds.graph.exists" on some GDS deployments.\nNot fixed here (CLAUDE.md SS1 scope).
   }

   :Streamlit bar chart / table\n(rendered in-process, not via the FastAPI app);
   stop
   @enduml
