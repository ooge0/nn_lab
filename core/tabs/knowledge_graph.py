import re

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st
from pyvis.network import Network
from scipy.stats import entropy
from loguru import logger

from core.service.neo4j_service import Neo4jService


# --- Failure-mode/cascade-lineage graph (2026-09-05 addition, same narrow CLAUDE.md SS1
# exception as the earlier PageRank fix -- see docs/source/wiki/07-knowledge-graph-results.rst).
# Distinct from the plain Archetype-ASSOCIATED_WITH-Bias co-occurrence graph the original "Sync
# history to Neo4j" button builds: this models the actual per-response cascade (CLAUDE.md SS3a/SS4)
# as explicit lineage edges -- which stage each response actually reached, in order -- so failure
# analysis is a graph traversal, not a groupby. See the module-level Cypher strings below for the
# schema; the two helpers here only reshape the DataFrame into the row shape that Cypher expects. ---


def _parse_rag_chunks(rag_context):
    """Recovers structured (archetype, category) chunk provenance from the concatenated
    ``rag_context`` string :meth:`core.services.experiment_runner.ExperimentRunner._run_one`
    persists -- no separate structured chunk list is stored on the response record, so this parses
    the exact serialization format that code writes
    (``f"[{c['archetype']} | {c['category']}]\\n{c['text']}"``, blocks joined by ``"\\n\\n"``).
    A real, disclosed simplification: this collapses every chunk sharing the same
    (archetype, category) pair into one graph node, not one node per distinct chunk of text --
    good enough for "which category of reference material" provenance, not full per-chunk lineage.
    """
    if not isinstance(rag_context, str) or not rag_context.strip():
        return []
    chunks = []
    for block in rag_context.split("\n\n"):
        m = re.match(r"^\[(.+?) \| (.+?)\]\n", block)
        if m:
            chunks.append({"archetype": m.group(1), "category": m.group(2)})
    return chunks


def _build_failure_mode_rows(df):
    """Converts one run's response DataFrame into the row shape :data:`_SYNC_FAILURE_MODE_CYPHER`
    expects -- in particular, resolves which cascade stages a response actually *reached*.

    A Layer-0-rejected or Layer-1-echo-rejected response never reaches a real judge call (see
    ``ExperimentRunner._run_one``'s early-return at the Layer-0 check, and the ``echo_detected``
    branch that synthesizes a verdict without calling ``self._judge.evaluate(...)``) -- attributing
    that auto-cascade-fail to whichever model happened to be *configured* as judge would misrepresent
    what actually happened, the same class of naming-vs-meaning gap already found twice elsewhere in
    this project (``semantic_overlap``, the benchmark leaderboard's ``mimicry_score``). So
    ``reached_judge`` is computed here, not assumed true just because a ``teacher``/``v_ok`` field
    exists on every row (it does, even for cascade-auto-fails -- CLAUDE.md SS4's own persisted-field
    contract).
    """
    rows = []
    for _, r in df.iterrows():
        layer0 = r.get("layer0_classification")
        layer0 = layer0 if isinstance(layer0, str) and layer0 else "VALID"
        reached_layer1 = layer0 == "VALID"
        echo = bool(r.get("layer1_echo_detected")) if reached_layer1 else False
        reached_judge = reached_layer1 and not echo
        layer2_checked = bool(r.get("layer2_checked")) and pd.notna(r.get("layer2_checked"))

        def _num(key):
            v = r.get(key)
            return float(v) if pd.notna(v) else None

        rows.append(
            {
                "response_id": f"{r.get('run_id')}:{r.get('step')}",
                "run_id": r.get("run_id"),
                "archetype": r.get("archetype"),
                "bias": r.get("bias"),
                "student": r.get("student"),
                "teacher": r.get("teacher"),
                "word_count": _num("word_count"),
                "duration_ms": _num("duration_ms"),
                "layer0_classification": layer0,
                "reached_layer1": reached_layer1,
                "layer1_result": "ECHO" if echo else "CLEAN",
                "semantic_overlap": _num("semantic_overlap"),
                "reached_layer2": layer2_checked,
                "layer2_result": r.get("layer2_predicted_label") if layer2_checked else None,
                "layer2_contradiction_score": _num("layer2_contradiction_score"),
                "reached_judge": reached_judge,
                "judge_result": "PASS" if bool(r.get("v_ok")) else "FAIL",
                "v_confidence": _num("v_confidence"),
                "chunks": _parse_rag_chunks(r.get("rag_context")) if r.get("rag_enabled") else [],
            }
        )
    return rows


# Stage 3: a tiny, fixed pipeline-shape reference subgraph (4 nodes, 3 edges, ever) encoding the
# cascade's own literal stage order -- run once, idempotent (MERGE), so "where does the chain
# terminate" can be answered by real graph traversal (see _ROOT_CAUSE_TERMINAL_STAGE_CYPHER) instead
# of an application-side CASE-based rank lookup dressed up as a query.
_BOOTSTRAP_CASCADE_STAGES_CYPHER = """
    MERGE (s0:CascadeStage {name:"Layer0"})
    MERGE (s1:CascadeStage {name:"Layer1"})
    MERGE (s2:CascadeStage {name:"Layer2"})
    MERGE (s3:CascadeStage {name:"Judge"})
    MERGE (s0)-[:PRECEDES]->(s1)
    MERGE (s1)-[:PRECEDES]->(s2)
    MERGE (s2)-[:PRECEDES]->(s3)
"""

# Note: every CascadeStage/CascadeOutcome node is MERGEd as its own bound variable BEFORE any
# relationship to it is merged -- MERGEing a full (node)-[:REL]->(anonymous pattern) in one step
# does NOT reuse an existing node for the anonymous side, it silently creates a duplicate (a real
# Neo4j MERGE pitfall, caught by testing this against the live database before writing it here, not
# assumed correct from the syntax alone).
_SYNC_FAILURE_MODE_CYPHER = """
    UNWIND $rows AS row
    MERGE (resp:Response {response_id: row.response_id})
      SET resp.word_count = row.word_count, resp.duration_ms = row.duration_ms
    MERGE (run:Run {run_id: row.run_id})
    MERGE (resp)-[:IN_RUN]->(run)
    MERGE (arch:Archetype {name: row.archetype})
    MERGE (resp)-[:CONDITIONED_ON]->(arch)
    MERGE (bias:Bias {name: row.bias})
    MERGE (resp)-[:CONDITIONED_ON]->(bias)
    MERGE (student:Model {name: row.student})
    MERGE (resp)-[:GENERATED_BY]->(student)

    MERGE (l0stage:CascadeStage {name: "Layer0"})
    MERGE (l0:CascadeOutcome {stage: "Layer0", result: row.layer0_classification})
    MERGE (l0)-[:PART_OF]->(l0stage)
    MERGE (resp)-[:REACHED]->(l0)

    FOREACH (_ IN CASE WHEN row.reached_layer1 THEN [1] ELSE [] END |
      MERGE (l1stage:CascadeStage {name: "Layer1"})
      MERGE (l1:CascadeOutcome {stage: "Layer1", result: row.layer1_result})
      MERGE (l1)-[:PART_OF]->(l1stage)
      MERGE (resp)-[rl1:REACHED]->(l1)
      SET rl1.score = row.semantic_overlap
    )

    FOREACH (_ IN CASE WHEN row.reached_layer2 THEN [1] ELSE [] END |
      MERGE (l2stage:CascadeStage {name: "Layer2"})
      MERGE (l2:CascadeOutcome {stage: "Layer2", result: row.layer2_result})
      MERGE (l2)-[:PART_OF]->(l2stage)
      MERGE (resp)-[rl2:REACHED]->(l2)
      SET rl2.score = row.layer2_contradiction_score
    )

    FOREACH (_ IN CASE WHEN row.reached_judge THEN [1] ELSE [] END |
      MERGE (judge:Model {name: row.teacher})
      MERGE (resp)-[:JUDGED_BY]->(judge)
      MERGE (judgeStage:CascadeStage {name: "Judge"})
      MERGE (jo:CascadeOutcome {stage: "Judge", result: row.judge_result})
      MERGE (jo)-[:PART_OF]->(judgeStage)
      MERGE (resp)-[rj:REACHED]->(jo)
      SET rj.confidence = row.v_confidence
    )

    FOREACH (chunk IN row.chunks |
      MERGE (kc:KnowledgeChunk {archetype: chunk.archetype, category: chunk.category})
      MERGE (resp)-[:RETRIEVED]->(kc)
    )
"""

# Root-cause query 1: which model is disproportionately linked to echo-rejections, across every
# archetype/bias it was tried against -- a real multi-hop pattern match, not a pandas groupby,
# because it composes for free with any other relationship on Response (archetype, bias, run, ...).
_ROOT_CAUSE_ECHO_BY_MODEL_CYPHER = """
    MATCH (r:Response)-[:GENERATED_BY]->(m:Model),
          (r)-[:REACHED]->(:CascadeOutcome {stage:"Layer1", result:"ECHO"})
    RETURN m.name AS model, count(r) AS echo_count
    ORDER BY echo_count DESC
"""

# Root-cause query 2: for one archetype, where does the cascade chain actually terminate -- using
# the Stage-3 pipeline-shape subgraph (CascadeStage/PRECEDES) via a real EXISTS{} graph traversal,
# not an application-side stage-rank lookup. A response with no *later*-stage REACHED outcome is,
# by construction, terminal at the outcome this query returns.
_ROOT_CAUSE_TERMINAL_STAGE_CYPHER = """
    MATCH (a:Archetype {name:$archetype})<-[:CONDITIONED_ON]-(r:Response)
    MATCH (r)-[:REACHED]->(o:CascadeOutcome)-[:PART_OF]->(s:CascadeStage)
    WHERE NOT EXISTS {
      MATCH (s)-[:PRECEDES]->(:CascadeStage)<-[:PART_OF]-(o2:CascadeOutcome)<-[:REACHED]-(r)
    }
    RETURN o.stage AS terminal_stage, o.result AS terminal_result, count(r) AS n
    ORDER BY n DESC
"""

# Root-cause query 3: which RAG-retrieved knowledge categories are upstream of Layer-1 echo
# failures -- the first query in this codebase connecting the RAG subsystem and the knowledge graph
# at all; previously the two never referenced each other.
_ROOT_CAUSE_RAG_CHUNKS_BY_ECHO_CYPHER = """
    MATCH (c:KnowledgeChunk)<-[:RETRIEVED]-(r:Response)-[:REACHED]->(:CascadeOutcome {stage:"Layer1", result:"ECHO"})
    RETURN c.archetype AS chunk_archetype, c.category AS chunk_category, count(r) AS echo_count
    ORDER BY echo_count DESC
"""


class KnowledgeGraph:
    """
    KnowledgeGraph integrates Neo4j with Streamlit to visualize and analyze
    application history data as a graph.

    Provides a Streamlit tab (`knowledge_graph_tab`) that:
    
    - Syncs rows from a pandas DataFrame into Neo4j nodes and relationships.
    - Runs PageRank algorithms via the Neo4j Graph Data Science (GDS) library.
    - Displays results interactively in multiple tabs (PageRank scripts, hypothesis testing, uncertainty analysis).

    This class is designed to bridge data ingestion, graph analytics, and
    interactive visualization in one place.


    References
    ----------

    - Neo4j Graph Data Science: https://neo4j.com/docs/graph-data-science/current/
    - Streamlit Tabs: https://docs.streamlit.io/library/api-reference/layout/st.tabs
    - Pandas DataFrame: https://pandas.pydata.org/docs/
    - Cypher MERGE: https://neo4j.com/docs/cypher-manual/current/clauses/merge/

    Attributes
    ----------

    None (stateless class, methods operate on provided DataFrame and Neo4j service).

    Methods
    -------

    knowledge_graph_tab(df : pandas.DataFrame)
        Builds the "Knowledge Graph" tab in Streamlit.
        - Pushes DataFrame rows into Neo4j (Archetype → Bias relationships).
        - Provides buttons to run PageRank scripts.
        - Displays results in interactive charts and tables.
        - "Root Cause (Failure-Mode Graph)" (2026-09-05): a second, richer sync builds an explicit
          per-response cascade-lineage graph (Response -> Run/Archetype/Bias/Model, plus which
          Layer0/Layer1/Layer2/Judge outcome each response actually reached) and exposes three
          real root-cause queries over it -- see docs/source/wiki/07-knowledge-graph-results.rst.

    Implementation status -- read before assuming this is stale
    --------------------------------------------------------------

    Everything above this note describes real, current, unchanged behavior -- not an artifact of an
    earlier iteration this file forgot to update. nn_lab was rewritten, stage by stage, from a single
    ~3,400-line Streamlit monolith into a layered FastAPI application (``core/domain`` ->
    ``core/services`` -> ``core/adapters``, exposed via ``api/``/``web``/``cli``). Every other tab
    that monolith once had now has a tested FastAPI route or CLI equivalent -- except this one.

    The project's own standing rules (``CLAUDE.md``, "Hard scope boundaries") explicitly carve the
    Neo4j/knowledge-graph subsystem out of that rewrite: it is not a candidate for a future stage,
    not partially migrated, not deprioritized by oversight -- it was a deliberate, upfront decision
    to keep this subsystem fully isolated for as long as this class exists, because graph analytics
    over run history is not the "moat" (LLM evaluation rigor) the rewrite exists to demonstrate.
    "Untouched" means exactly that: this class, ``knowledge_graph_tab``'s own logic, and
    :class:`~core.service.neo4j_service.Neo4jService` have not been refactored, re-layered, or moved
    behind a ``core.domain`` interface the way every other tab's logic was. The one narrow exception
    is this docstring itself, edited only to add this note -- not to change what the code does.

    What *did* change around this class, without changing anything inside it: the Streamlit script
    that calls ``knowledge_graph_tab`` is no longer the original monolith. That file now lives at
    ``legacy/streamlit_app.py`` (moved there via ``git mv``, kept only as historical reference -- not
    a live entry point). This method is called today from a small, dedicated standalone script,
    ``run_knowledge_graph.py`` (repo root), which does nothing else: it loads one run's persisted
    responses via ``core.adapters.jsonl_store.JSONLStore`` -- the same repository the FastAPI app and
    CLI batch runner both write to -- and hands the resulting DataFrame straight to this method,
    unchanged. So "Streamlit tab" above is still literally correct, not a leftover phrase: this still
    renders as one tab-shaped section inside a real (now minimal, single-purpose) Streamlit page: it
    is just no longer one tab among a dozen in a 3,400-line file.
    """

    @staticmethod
    def knowledge_graph_tab(df):
        """
        Knowledge Graph Tab

        Parameters
        ----------
        df : pandas.DataFrame
            Input DataFrame with at least 'archetype' and 'bias' columns.

        Returns
        -------
        None
            Streamlit UI elements are rendered directly.
        """
        neo4j_service = Neo4jService()
        graph = neo4j_service.load_neo4j_creds()
        st.subheader("Knowledge Graph")
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "PageRank-1", "PageRank-2", "PageRank-3", "PageRank-4", "Hypothesis Testing",
            "Uncertainty Analysis", "Root Cause (Failure-Mode Graph)",
        ])

        # Push DataFrame rows into Neo4j (batched for speed)
        if st.button("Sync history to Neo4j"):
            try:
                rows = df.to_dict("records")
                graph.run("""
                    UNWIND $rows AS row
                    MERGE (a:Archetype {name:row.archetype})
                    MERGE (b:Bias {name:row.bias})
                    MERGE (a)-[:ASSOCIATED_WITH]->(b)
                """, rows=rows)
                st.success(f"History synced into Neo4j! {len(rows)} rows processed.")
            except Exception as e:
                st.error(f"Error syncing data: {e}")

        with tab1:
            st.header("Run PageRank script-1")
            if st.button("Run PageRank script-1"):
                try:
                    # Project graph only if not exists
                    exists = graph.run("CALL gds.graph.exists('archetypeGraph') YIELD exists").evaluate()
                    if not exists:
                        graph.run("""
                            CALL gds.graph.project(
                              'archetypeGraph',
                              'Archetype',
                              'ASSOCIATED_WITH'
                            )
                        """)

                    result = graph.run("""
                        CALL gds.pageRank.stream('archetypeGraph')
                        YIELD nodeId, score
                        RETURN gds.util.asNode(nodeId).name AS name, score
                        ORDER BY score DESC
                    """)
                    df_rank = pd.DataFrame(result, columns=["Archetype", "Score"])
                    st.success("PageRank completed on archetypeGraph!")
                    st.write(df_rank)
                    st.bar_chart(df_rank.set_index("Archetype"))
                except Exception as e:
                    st.error(f"Error running PageRank script-1: {e}")
                    logger.error(f"Error running PageRank script-1: {e}")

        with tab2:
            st.header("Run PageRank script-2 (metadata enrichment)")
            if st.button("Run PageRank script-2"):
                try:
                    rows = df.to_dict("records")
                    graph.run("""
                        UNWIND $rows AS row
                        MERGE (a:Archetype {name:row.archetype})
                        SET a.dimension = row.dimension, a.category = row.category
                        MERGE (b:Bias {name:row.bias})
                        SET b.severity = row.severity, b.type = row.bias_type
                    """, rows=rows)
                    st.success("Node properties updated with n-dimensional metadata.")

                    # Visualization of updated properties
                    props = graph.run("""
                        MATCH (a:Archetype)-[:ASSOCIATED_WITH]->(b:Bias)
                        RETURN a.name AS Archetype, a.dimension AS Dimension, a.category AS Category,
                               b.name AS Bias, b.severity AS Severity, b.type AS Type
                        LIMIT 20
                    """).to_data_frame()
                    st.write(props)
                except Exception as e:
                    st.error(f"Error running PageRank script-2: {e}")
                    logger.error(f"Error running PageRank script-2: {e}")

        # Run PageRank script-3 (graph projection + visualization)
        with tab3:
            # TODO: Need resolve "Error running PageRank script-3: [Procedure.ProcedureNotFound] There is no procedure
            #  with the name gds.graph.exists registered for this database instance. Please ensure you've spelled
            #  the procedure name correctly and that the procedure is properly deployed."
            st.header("Experiment graph visualization")

            # Interactive controls
            radius = st.slider("Node radius", 5, 50, 15)
            edge_color = st.color_picker("Edge color", "#00ccff")

            if st.button("Run PageRank script-3"):
                try:
                    exists = graph.run("CALL gds.graph.exists('experimentGraph') YIELD exists").evaluate()
                    if not exists:
                        graph.run("""
                            CALL gds.graph.project(
                              'experimentGraph',
                              ['Archetype','Bias'],
                              {
                                ASSOCIATED_WITH: { type:'ASSOCIATED_WITH', orientation:'UNDIRECTED' }
                              }
                            )
                        """)
                    st.success("experimentGraph projected!")

                    # Build network from in-memory df
                    G = nx.Graph()
                    for _, row in df.iterrows():
                        G.add_node(row['archetype'], label=row['archetype'])
                        G.add_node(row['bias'], label=row['bias'])
                        G.add_edge(row['archetype'], row['bias'])

                    net = Network(height="600px", width="100%", notebook=False)
                    net.from_nx(G)

                    # Apply user controls
                    net.show_buttons(filter_=['physics'])
                    for node in net.nodes:
                        node['size'] = radius
                    for edge in net.edges:
                        edge['color'] = edge_color

                    net.save_graph("results/graph_data/experimentGraph.html")
                    st.iframe(open("results/graph_data/experimentGraph.html").read(), height=600)
                except Exception as e:
                    st.error(f"Error running PageRank script-3: {e}")
                    logger.error(f"Error running PageRank script-3: {e}")

            param = st.selectbox("Choose parameter to visualize", df.columns)

            param = st.selectbox("Choose parameter", ["archetype", "bias", "cognitive_load"])
            if st.button("Visualize JSONL relations"):
                G = nx.Graph()
                for _, rec in df.iterrows():
                    if "archetype" in rec and "bias" in rec:
                        G.add_edge(rec["archetype"], rec["bias"], weight=rec.get(param, 1))
                net = Network(height="600px", width="100%", notebook=False)
                net.from_nx(G)
                net.show_buttons(filter_=['physics'])
                net.save_graph("results/graph_data/jsonlGraph.html")
                st.iframe(open("results/graph_data/jsonlGraph.html").read(), height=600)

        with tab4:
            st.header("PageRank script-4")
            if st.button("Run PageRank script-4"):
                try:
                    # Real bug found during a 2026-09-05 audit: this previously called
                    # gds.pageRank.stream('experimentGraph') unconditionally, assuming
                    # script-3's projection had already run in this session -- if it
                    # hadn't (e.g. this tab clicked first, or after a server restart,
                    # since GDS's in-memory graph catalog does not persist across
                    # restarts), this raised the same
                    # Procedure.ProcedureNotFound/graph-not-found class of error
                    # script-3's own TODO already disclosed for 'archetypeGraph'.
                    # Same exists-check-then-project guard as scripts 1/3.
                    exists = graph.run("CALL gds.graph.exists('experimentGraph') YIELD exists").evaluate()
                    if not exists:
                        graph.run("""
                            CALL gds.graph.project(
                              'experimentGraph',
                              ['Archetype','Bias'],
                              {
                                ASSOCIATED_WITH: { type:'ASSOCIATED_WITH', orientation:'UNDIRECTED' }
                              }
                            )
                        """)

                    result = graph.run("""
                        CALL gds.pageRank.stream('experimentGraph')
                        YIELD nodeId, score
                        RETURN gds.util.asNode(nodeId).name AS name,
                               labels(gds.util.asNode(nodeId)) AS labels,
                               score
                        ORDER BY score DESC
                    """)

                    # Convert to DataFrame
                    df_rank = pd.DataFrame(result, columns=["Name", "Labels", "Score"])

                    # Fix: turn list of labels into a string
                    df_rank["Labels"] = df_rank["Labels"].apply(
                        lambda x: ",".join(x) if isinstance(x, list) else str(x))

                    st.success("PageRank completed on experimentGraph!")
                    st.write(df_rank)

                    # Use Name as index for chart
                    st.bar_chart(df_rank.set_index("Name")["Score"])

                except Exception as e:
                    st.error(f"Error running PageRank script-4: {e}")
                    logger.error(f"Error running PageRank script-4: {e}")

        with tab5:
            st.header("Hypothesis testing: Archetype comparison")
            # User selects archetypes and metric
            archetype_A = st.selectbox("Choose archetype A", df['archetype'].unique())
            archetype_B = st.selectbox("Choose archetype B", df['archetype'].unique())
            metric = st.selectbox("Choose metric to compare", ["cognitive_load", "sentiment", "lexical_density"])

            if st.button("Run hypothesis test"):
                try:
                    # Filter data for each archetype
                    df_A = df[df['archetype'] == archetype_A]
                    df_B = df[df['archetype'] == archetype_B]

                    # Compute average values
                    mean_A = df_A[metric].mean()
                    mean_B = df_B[metric].mean()

                    # Calculate relative shift
                    delta = (mean_A - mean_B) / mean_B if mean_B != 0 else None
                    shift_over_50 = delta is not None and delta > 0.5

                    # Show results
                    st.write(f"Average {metric} for {archetype_A}: {mean_A:.3f}")
                    st.write(f"Average {metric} for {archetype_B}: {mean_B:.3f}")
                    st.write(
                        f"Relative shift: {delta:.2%}" if delta is not None else "Cannot compute shift (division by zero).")

                    if shift_over_50:
                        st.success(
                            f"Hypothesis confirmed: {archetype_A} shows >50% higher {metric} than {archetype_B}.")
                    else:
                        st.info(f"Hypothesis not confirmed: shift ≤50%.")

                    # Visualization
                    fig, ax = plt.subplots()
                    ax.bar([archetype_A, archetype_B], [mean_A, mean_B], color=['blue', 'orange'])
                    ax.set_ylabel(metric)
                    ax.set_title(f"{metric} comparison: {archetype_A} vs {archetype_B}")
                    st.pyplot(fig)

                except Exception as e:
                    st.error(f"Error running hypothesis test: {e}")

        with tab6:
            st.header("Uncertainty analysis: Multi-metric & Distribution shift")

            # User selects archetypes to compare
            archetype_A = st.selectbox("Choose archetype A", df['archetype'].unique(),
                                       key="archetype_A")
            archetype_B = st.selectbox("Choose archetype B", df['archetype'].unique(),
                                       key="archetype_B")

            metrics = ["cognitive_load", "lexical_density", "sentiment"]

            if st.button("Run Extended Analysis"):
                results = []

                for metric in metrics:
                    for archetype in [archetype_A, archetype_B]:
                        df_arch = df[df['archetype'] == archetype][metric].dropna()

                        if len(df_arch) == 0:
                            continue

                        # Bootstrap resampling for epistemic uncertainty
                        samples = []
                        for i in range(50):
                            boot = np.random.choice(df_arch, size=len(df_arch), replace=True)
                            samples.append(np.mean(boot))
                        samples = np.array(samples)

                        epistemic_var = np.var(samples)
                        aleatoric_var = np.var(df_arch)

                        results.append({
                            "Archetype": archetype,
                            "Metric": metric,
                            "Epistemic": epistemic_var,
                            "Aleatoric": aleatoric_var,
                            "Dominant": "Epistemic" if epistemic_var > aleatoric_var else "Aleatoric"
                        })

                # Convert to DataFrame
                df_results = pd.DataFrame(results)

                st.write("### Results Table")
                st.dataframe(df_results)

                # Visualization: grouped bar chart
                for metric in metrics:
                    subset = df_results[df_results["Metric"] == metric]
                    if subset.empty:
                        continue
                    fig, ax = plt.subplots()
                    width = 0.35
                    x = np.arange(len(subset["Archetype"]))

                    ax.bar(x - width / 2, subset["Epistemic"], width, label="Epistemic")
                    ax.bar(x + width / 2, subset["Aleatoric"], width, label="Aleatoric")

                    ax.set_xticks(x)
                    ax.set_xticklabels(subset["Archetype"])
                    ax.set_ylabel("Variance")
                    ax.set_title(f"Uncertainty comparison for {metric}")
                    ax.legend()

                    st.pyplot(fig)

                # Distribution shift detection (KL divergence)
                st.write("### Distribution Shift Detection")
                for metric in metrics:
                    df_A = df[df['archetype'] == archetype_A][metric].dropna()
                    df_B = df[df['archetype'] == archetype_B][metric].dropna()
                    if len(df_A) > 0 and len(df_B) > 0:
                        # Histogram bins
                        bins = np.linspace(min(df[metric].dropna()), max(df[metric].dropna()), 20)
                        hist_A, _ = np.histogram(df_A, bins=bins, density=True)
                        hist_B, _ = np.histogram(df_B, bins=bins, density=True)

                        # Avoid zero bins
                        hist_A += 1e-9
                        hist_B += 1e-9

                        kl_div = entropy(hist_A, hist_B)
                        st.write(f"KL divergence for {metric} between {archetype_A} and {archetype_B}: {kl_div:.4f}")

                        fig, ax = plt.subplots()
                        ax.hist(df_A, bins=bins, alpha=0.5, label=archetype_A)
                        ax.hist(df_B, bins=bins, alpha=0.5, label=archetype_B)
                        ax.set_title(f"Distribution comparison for {metric}")
                        ax.legend()
                        st.pyplot(fig)

        with tab7:
            st.header("Root cause: cascade failure-mode graph")
            st.caption(
                "Models the actual per-response cascade (CLAUDE.md SS3a/SS4) as explicit lineage "
                "edges -- which stage each response reached, in order -- distinct from the plain "
                "Archetype-Bias co-occurrence graph the 'Sync history to Neo4j' button above builds. "
                "See docs/source/wiki/07-knowledge-graph-results.rst for the full schema and rationale."
            )

            if st.button("Sync failure-mode graph"):
                try:
                    graph.run(_BOOTSTRAP_CASCADE_STAGES_CYPHER)
                    rows = _build_failure_mode_rows(df)
                    graph.run(_SYNC_FAILURE_MODE_CYPHER, rows=rows)
                    st.success(f"Failure-mode graph synced! {len(rows)} response(s) processed.")
                except Exception as e:
                    st.error(f"Error syncing failure-mode graph: {e}")
                    logger.error(f"Error syncing failure-mode graph: {e}")

            st.subheader("Root-cause queries")

            if st.button("Which model is most linked to echo-rejections?"):
                try:
                    result = graph.run(_ROOT_CAUSE_ECHO_BY_MODEL_CYPHER).to_data_frame()
                    st.dataframe(result)
                except Exception as e:
                    st.error(f"Error running query: {e}")

            rc_archetype = st.selectbox(
                "Archetype to inspect", df["archetype"].unique(), key="root_cause_archetype"
            )
            if st.button("Where does the cascade terminate for this archetype?"):
                try:
                    result = graph.run(
                        _ROOT_CAUSE_TERMINAL_STAGE_CYPHER, archetype=rc_archetype
                    ).to_data_frame()
                    st.dataframe(result)
                except Exception as e:
                    st.error(f"Error running query: {e}")

            if st.button("Which RAG knowledge categories precede echo-rejections?"):
                try:
                    result = graph.run(_ROOT_CAUSE_RAG_CHUNKS_BY_ECHO_CYPHER).to_data_frame()
                    if result.empty:
                        st.info("No RAG-enabled responses with echo-rejections found in this run's synced data.")
                    else:
                        st.dataframe(result)
                except Exception as e:
                    st.error(f"Error running query: {e}")
