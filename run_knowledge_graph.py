"""
run_knowledge_graph.py
=========================

Standalone Neo4j knowledge-graph explorer -- Stage 16 extracted this from
``streamlit_app.py``'s ``tab_knowledge_graph`` now that every other legacy
tab has a FastAPI equivalent (Stages 5-15). This is the only surviving
Streamlit entry point going forward; ``streamlit_app.py`` itself moved to
``legacy/streamlit_app.py`` (kept for reference, no longer the way to run
anything -- see ``legacy/README.md``).

Per CLAUDE.md's constraint 1, the Neo4j subsystem stays untouched:
``core/service/neo4j_service.py``, ``utils/other/neo4j_services.py``, and
``core/tabs/knowledge_graph.py`` are imported, not modified -- with one exception, 2026-09-05: the
failure-mode/cascade-lineage graph and its 3 root-cause queries were promoted out of
``core/tabs/knowledge_graph.py`` into the layered FastAPI architecture (``/knowledge_graph``, see
``core/adapters/neo4j_repo.py``). What's left in ``core/tabs/knowledge_graph.py`` -- the PageRank
scripts, the plain Archetype/Bias sync, Hypothesis Testing, Uncertainty Analysis -- is exactly as
untouched as before.

Unlike the legacy tab (which read ``st.session_state.history``, populated
by ``tab_gen``'s live in-session generation), this script has no generation
flow of its own -- it loads a run's persisted responses via the same
``JSONLStore`` (Stage 3) the FastAPI app and CLI batch runner (Stage 15)
both already use, so any run generated through either front end is
reachable here too.

Run with::

    streamlit run run_knowledge_graph.py
"""

import pandas as pd
import streamlit as st

from core.adapters.jsonl_store import JSONLStore
from core.tabs.knowledge_graph import KnowledgeGraph
from utils.other.neo4j_services import start_neo4j

st.set_page_config(page_title="nn_lab -- Knowledge Graph", layout="wide")
start_neo4j()

st.title("Knowledge Graph (Neo4j)")
st.caption(
    "Standalone Neo4j graph explorer -- PageRank scripts, the plain Archetype/Bias sync, "
    "Hypothesis Testing, and Uncertainty Analysis only. The failure-mode/cascade-lineage graph "
    "and its root-cause queries moved to the FastAPI app's /knowledge_graph page (2026-09-05); "
    "every other tab has moved to the FastAPI app (`uvicorn api.app:app --reload`) or the CLI "
    "(`python -m cli.run_experiment`) -- this page exists purely because what's left here stays "
    "on Neo4j, out of scope for the rewrite (CLAUDE.md constraint 1)."
)

repository = JSONLStore()
runs = repository.list_runs()

if not runs:
    st.info(
        "No experiment runs found yet. Generate one first via the FastAPI app's "
        "/experiments page, or `python -m cli.run_experiment --config <path>`."
    )
else:
    run_labels = {run.run_id: f"{run.run_id} ({run.started_at}, {run.total_tasks} tasks)" for run in runs}
    selected_run_id = st.selectbox("Run", options=list(run_labels), format_func=lambda rid: run_labels[rid])

    responses = repository.load_responses(selected_run_id)
    df = pd.json_normalize(responses)
    KnowledgeGraph.knowledge_graph_tab(df)
