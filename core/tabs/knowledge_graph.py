import streamlit as st
import configparser
from py2neo import Graph
import pandas as pd


def knowledge_graph_tab(df):
    """
    About:
        Renders an interactive Knowledge Graph dashboard component within a Streamlit tab.
        This function handles ingestion of flat tabular application historical logs, maps
        them to a highly interconnected semantic graph network, handles batch structural updates
        via atomic Cypher transactions, and executes localized algorithmic calculations
        (PageRank) directly on the active Neo4j graph processing unit.

    Parameters:
        df (pandas.DataFrame): A structural collection containing application execution metrics.
            Required Columns:
                - 'archetype' (str): Name/Identifier of the behavioral archetype (Source node).
                - 'bias' (str): Identified cognitive or systemic bias signature (Target node).

    Returns:
        None: Renders UI components, stateful progress monitoring components, and graphical
              bar charts directly into the active Streamlit runtime frame viewport.

    References:
        Cypher:
            A declarative graph query language optimized for expressive, highly performant
            graph database pattern matching and navigational traversals.
            Source: https://neo4j.com

        Neo4j:
            An open-source, enterprise-grade native graph database engine engineered to optimize
            and persist high-density relationships as first-class citizens.
            Source: https://github.com/neo4j/neo4j

        py2neo:
            A comprehensive client library and toolkit designed to seamlessly integrate Python
            applications with Neo4j using the binary Bolt network communication protocol.
            Source: https://github.com/py2neo/py2neo

        configparser:
            A native Python standard configuration file parser designed to read, store, and manage
            structured key-value credential properties from standardized INI-formatted files.
            Source: https://python.org

        APOC (Awesome Procedures on Cypher):
            A foundational utility plugin library packed with hundreds of practical procedures,
            data integrations, and advanced algorithms that extend native Cypher functionality.
            Source: https://github.com/neo4j/apoc

        PageRank Algorithm:
            A structural link-analysis algorithm that evaluates node importance within a network topology
            by calculating transitive vector probability scores across directional paths.
            Source: https://neo4j.com
    """

    # Load creds
    config = configparser.ConfigParser()
    config.read("config.ini")
    uri = config["neo4j"]["uri"]
    user = config["neo4j"]["user"]
    password = config["neo4j"]["password"]
    graph = Graph(uri, auth=(user, password))

    st.subheader("Knowledge Graph")

    # Push DataFrame rows into Neo4j
    if st.button("Sync history to Neo4j"):
        progress_bar = st.progress(0)
        total = len(df)
        for i, row in df.iterrows():
            graph.run("""  
                MERGE (a:Archetype {name:$archetype})                
                MERGE (b:Bias {name:$bias})                
                MERGE (a)-[:ASSOCIATED_WITH]->(b)            """, archetype=row.get("archetype"), bias=row.get("bias"))

            # Console log for debugging
            print(f"Synced row {i + 1}/{total}: Archetype={row.get('archetype')} Bias={row.get('bias')}")

            # Update progress bar
            progress_bar.progress(int((i + 1) / total * 100))

        st.success(f"History synced into Neo4j! {total} rows processed.")

        # Run PageRank
    if st.button("Run PageRank"):
        result = graph.run("""  
            CALL apoc.algo.pageRank(              
              'MATCH (a:Archetype)-[:ASSOCIATED_WITH]->(b:Bias) RETURN id(a) as source, id(b) as target',              
              {iterations:20, dampingFactor:0.85}            
            )            
            YIELD node, score            
            RETURN node.name AS name, score            
            ORDER BY score DESC        """)
        df_rank = pd.DataFrame(result, columns=["Archetype", "Score"])
        st.write(df_rank)
        st.bar_chart(df_rank.set_index("Archetype"))