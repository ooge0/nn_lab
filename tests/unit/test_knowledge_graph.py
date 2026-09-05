"""
Unit tests for :mod:`core.tabs.knowledge_graph` -- the legacy, CLAUDE.md SS1-quarantined Neo4j
subsystem, exercised here for the first time (previously zero test coverage, confirmed by a
2026-09-05 audit). Runs the real :meth:`KnowledgeGraph.knowledge_graph_tab` Streamlit UI headlessly
via ``streamlit.testing.v1.AppTest`` and a fake, in-memory ``py2neo.Graph`` stand-in
(:class:`_FakeGraph`) -- no live Neo4j server, no Docker (this project has neither, by design).

This does not (and cannot, without a live server) prove the real Cypher/GDS calls succeed against
an actual Neo4j+GDS install -- that was verified manually, once, for real, during the same audit
(see ``docs/source/wiki/07-knowledge-graph-results.rst`` for the captured real output). What these
tests lock in instead is the thing a live-server test can't cheaply guard against regressing: the
*query construction and call ordering* -- which Cypher text is sent, with which parameters, and in
which sequence -- since that's exactly the class of bug the 2026-09-05 audit found (script-4 called
``gds.pageRank.stream`` without first checking/creating its graph projection, unlike scripts 1/3).

The failure-mode/cascade-lineage graph this module's tests originally also covered was promoted out
of ``core/tabs/knowledge_graph.py`` the same day (see that module's own docstring) into
:mod:`core.adapters.neo4j_repo` -- its tests moved with it, to
:mod:`tests.unit.test_neo4j_repo`. What remains here covers exactly what's still in this Streamlit
module: the plain Archetype/Bias co-occurrence sync and the 4 PageRank scripts.
"""

import pandas as pd
from streamlit.testing.v1 import AppTest


def _kg_tab_script(df):
    # AppTest.from_function extracts only this function's own source text and runs it standalone
    # (see streamlit.testing.v1.AppTest.from_function's own docstring: "must include any necessary
    # imports") -- knowledge_graph_tab itself is a real, normally-imported function once called
    # from here, so its own module's globals (Neo4jService, st, pd, np, nx, ...) resolve normally;
    # only this outer wrapper needs to be self-contained.
    from core.tabs.knowledge_graph import KnowledgeGraph

    KnowledgeGraph.knowledge_graph_tab(df)


class _FakeResult:
    """Stands in for whatever ``py2neo.Graph.run(...)`` returns -- different call sites in
    ``knowledge_graph_tab`` use it as a boolean (``.evaluate()``), a DataFrame
    (``.to_data_frame()``), or an iterable of row-tuples (``pd.DataFrame(result, columns=...)``).
    Only the branch actually exercised for a given query needs to be meaningful."""

    def __init__(self, evaluate_value=None, rows=None, dataframe=None):
        self._evaluate_value = evaluate_value
        self._rows = rows or []
        self._dataframe = dataframe

    def evaluate(self):
        return self._evaluate_value

    def to_data_frame(self):
        return self._dataframe if self._dataframe is not None else pd.DataFrame()

    def __iter__(self):
        return iter(self._rows)


class _FakeGraph:
    """Records every Cypher string + params sent via ``.run(...)``, in order, and returns a
    query-shape-appropriate :class:`_FakeResult` -- a real Neo4j/GDS deployment was already
    verified manually (see the results page); this is purely a query-construction/ordering check.
    """

    def __init__(self, graph_exists=False):
        self.calls: list[dict] = []
        self._graph_exists = graph_exists

    def run(self, query, **params):
        self.calls.append({"query": query, "params": params})
        q = " ".join(query.split())  # normalize whitespace for substring checks

        if "gds.graph.exists" in q:
            return _FakeResult(evaluate_value=self._graph_exists)
        if "gds.pageRank.stream" in q:
            return _FakeResult(
                rows=(
                    [("Neutral", 0.15), ("Detached", 0.15)]
                    if "archetypeGraph" in q
                    else [("Neutral", ["Archetype"], 1.05), ("formal", ["Bias"], 0.89)]
                )
            )
        if "RETURN a.name" in q:
            return _FakeResult(dataframe=pd.DataFrame({"Archetype": ["Neutral"], "Bias": ["formal"]}))
        return _FakeResult()


def _sample_df():
    return pd.DataFrame(
        [
            {
                "archetype": "Neutral",
                "bias": "formal",
                "dimension": "d1",
                "category": "c1",
                "severity": "low",
                "bias_type": "style",
                "cognitive_load": 0.4,
            },
            {
                "archetype": "Detached",
                "bias": "toxic",
                "dimension": "d2",
                "category": "c2",
                "severity": "high",
                "bias_type": "tone",
                "cognitive_load": 0.7,
            },
        ]
    )


def _run_and_click(monkeypatch, fake_graph, button_label):
    """Patches Neo4jService.load_neo4j_creds to return ``fake_graph``, runs
    ``knowledge_graph_tab`` headlessly, clicks the given tab's button, and re-runs -- the standard
    AppTest interaction pattern (a click schedules a rerun, it doesn't execute inline)."""
    monkeypatch.setattr("core.tabs.knowledge_graph.Neo4jService.load_neo4j_creds", lambda self: fake_graph)
    at = AppTest.from_function(_kg_tab_script, args=(_sample_df(),))
    at.run()
    # Buttons inside a specific st.tabs() context are still addressed via at.button, matched by
    # their visible label -- AppTest doesn't scope button() lookups by the enclosing tab.
    for b in at.button:
        if b.label == button_label:
            b.click().run()
            return at
    raise AssertionError(f"button {button_label!r} not found; saw {[b.label for b in at.button]}")


def test_sync_button_sends_the_real_merge_cypher_with_every_row(monkeypatch):
    """ "Sync history to Neo4j" sends one UNWIND/MERGE/MERGE/MERGE Cypher statement carrying every
    DataFrame row as the `$rows` parameter -- the exact query the real, manually-verified run used."""
    fake_graph = _FakeGraph()
    at = _run_and_click(monkeypatch, fake_graph, button_label="Sync history to Neo4j")

    assert len(fake_graph.calls) == 1
    call = fake_graph.calls[0]
    assert "UNWIND $rows AS row" in call["query"]
    assert "MERGE (a:Archetype {name:row.archetype})" in call["query"]
    assert "MERGE (b:Bias {name:row.bias})" in call["query"]
    assert "MERGE (a)-[:ASSOCIATED_WITH]->(b)" in call["query"]
    assert len(call["params"]["rows"]) == 2
    assert call["params"]["rows"][0]["archetype"] == "Neutral"
    assert not at.exception


def test_pagerank_script_1_projects_the_graph_only_when_it_does_not_already_exist(monkeypatch):
    """gds.graph.project is called before gds.pageRank.stream when archetypeGraph doesn't exist yet
    -- and is skipped (not re-projected) when it already does, matching GDS's own "project once,
    query many times" catalog model."""
    fake_graph = _FakeGraph(graph_exists=False)
    at = _run_and_click(monkeypatch, fake_graph, button_label="Run PageRank script-1")

    queries = [c["query"] for c in fake_graph.calls]
    assert any("gds.graph.exists" in q for q in queries)
    assert any("gds.graph.project" in q for q in queries)
    assert any("gds.pageRank.stream" in q for q in queries)
    # Ordering: exists-check and project both precede the actual PageRank stream call.
    stream_index = next(i for i, q in enumerate(queries) if "gds.pageRank.stream" in q)
    project_index = next(i for i, q in enumerate(queries) if "gds.graph.project" in q)
    assert project_index < stream_index
    assert not at.exception

    fake_graph_already_projected = _FakeGraph(graph_exists=True)
    _run_and_click(monkeypatch, fake_graph_already_projected, button_label="Run PageRank script-1")
    queries2 = [c["query"] for c in fake_graph_already_projected.calls]
    assert not any("gds.graph.project" in q for q in queries2)


def test_pagerank_script_4_now_projects_before_streaming_regression_fence(monkeypatch):
    """Regression fence for the real bug found in the 2026-09-05 audit: script-4 used to call
    gds.pageRank.stream('experimentGraph') with no exists-check/projection guard at all, unlike
    scripts 1/3 -- meaning it only ever worked by accident, if script-3 happened to run first in the
    same GDS session. Fixed to match the same exists-check-then-project pattern; this test fails
    loudly if that guard is ever removed again."""
    fake_graph = _FakeGraph(graph_exists=False)
    at = _run_and_click(monkeypatch, fake_graph, button_label="Run PageRank script-4")

    queries = [c["query"] for c in fake_graph.calls]
    assert any("gds.graph.exists" in q for q in queries), "script-4 must check the projection exists before streaming"
    assert any("gds.graph.project" in q for q in queries), "script-4 must create the projection when missing"
    stream_index = next(i for i, q in enumerate(queries) if "gds.pageRank.stream" in q)
    project_index = next(i for i, q in enumerate(queries) if "gds.graph.project" in q)
    assert project_index < stream_index, "projection must be created BEFORE streaming PageRank, not after/never"
    assert not at.exception


def test_pagerank_script_2_enriches_metadata_with_a_separate_merge_set_cypher(monkeypatch):
    """ "Run PageRank script-2" writes archetype/bias metadata via MERGE+SET (no GDS involved --
    plain Cypher property writes) and then reads it back via a separate MATCH query."""
    fake_graph = _FakeGraph()
    at = _run_and_click(monkeypatch, fake_graph, button_label="Run PageRank script-2")

    queries = [c["query"] for c in fake_graph.calls]
    assert any("SET a.dimension = row.dimension" in q for q in queries)
    assert any("SET b.severity = row.severity" in q for q in queries)
    assert any("MATCH (a:Archetype)-[:ASSOCIATED_WITH]->(b:Bias)" in q for q in queries)
    assert not at.exception
