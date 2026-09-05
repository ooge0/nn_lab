import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st
from pyvis.network import Network
from scipy.stats import entropy
from loguru import logger

from core.service.neo4j_service import Neo4jService


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
    behind a ``core.domain`` interface the way every other tab's logic was.

    **Third exception, 2026-09-05 -- a real logic change, not just a docstring one, and narrower
    than it might look:** the "Root Cause (Failure-Mode Graph)" tab this class briefly carried
    (added, then removed, the same day) has been **promoted out of this class entirely**, by
    explicit author decision, into the layered architecture --
    :class:`core.domain.interfaces.GraphRepository` + :class:`core.adapters.neo4j_repo
    .Neo4jGraphRepo` + ``api/routers/knowledge_graph.py`` + ``/knowledge_graph`` (a real FastAPI
    page now, not a Streamlit tab). Its Cypher was not rewritten, only moved -- see
    ``core/adapters/neo4j_repo.py``'s own docstring for exactly what's identical and what changed
    (the sync method now takes an explicit ``run_id`` parameter instead of a DataFrame column).
    This class's **remaining** tabs (PageRank scripts 1-4, the plain Archetype/Bias co-occurrence
    sync, Hypothesis Testing, Uncertainty Analysis) are **not** part of this promotion and remain
    exactly as untouched as before -- CLAUDE.md SS1's original quarantine still governs everything
    that's still in this file. Full record: ``docs/source/wiki/07-knowledge-graph-results.rst``.

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
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "PageRank-1", "PageRank-2", "PageRank-3", "PageRank-4", "Hypothesis Testing",
            "Uncertainty Analysis",
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
