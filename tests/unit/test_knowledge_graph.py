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
"""

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from core.tabs.knowledge_graph import _build_failure_mode_rows, _parse_rag_chunks


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


# --- Failure-mode/cascade-lineage graph (2026-09-05) -----------------------------------------


def test_parse_rag_chunks_recovers_archetype_and_category_from_the_real_serialized_format():
    """Matches the exact format ExperimentRunner._run_one writes:
    f"[{archetype} | {category}]\\n{text}", blocks joined by "\\n\\n"."""
    ctx = "[baseline | Behavior]\nSome behavior text.\n\n[paranoid | Speech]\nSome speech text."
    assert _parse_rag_chunks(ctx) == [
        {"archetype": "baseline", "category": "Behavior"},
        {"archetype": "paranoid", "category": "Speech"},
    ]


def test_parse_rag_chunks_handles_empty_none_and_malformed_input():
    assert _parse_rag_chunks("") == []
    assert _parse_rag_chunks(None) == []
    assert _parse_rag_chunks(float("nan")) == []
    assert _parse_rag_chunks("not the expected bracket format at all") == []


def test_build_rows_layer0_rejected_response_reaches_nothing_past_layer0():
    """A Layer-0-rejected response never reaches Layer1/Layer2/Judge in the real pipeline
    (ExperimentRunner._run_one's early-return) -- its row must reflect that, not default to
    'reached' just because v_ok/teacher fields exist on every row regardless."""
    df = pd.DataFrame(
        [
            {
                "run_id": "run-a",
                "step": "1/10",
                "archetype": "Neutral",
                "bias": "formal",
                "student": "qwen:latest",
                "teacher": "qwen:latest",
                "layer0_classification": "TRUNCATED",
                "layer1_echo_detected": False,
                "v_ok": False,
                "v_confidence": 1.0,
                "rag_enabled": False,
            }
        ]
    )
    row = _build_failure_mode_rows(df)[0]
    assert row["layer0_classification"] == "TRUNCATED"
    assert row["reached_layer1"] is False
    assert row["reached_layer2"] is False
    assert row["reached_judge"] is False
    assert row["chunks"] == []


def test_build_rows_echo_rejected_response_can_still_reach_layer2_but_never_the_judge():
    """Real, non-obvious pipeline behavior, confirmed by reading ExperimentRunner._run_one
    directly: Layer 2's hallucination check runs BEFORE the echo-vs-real-judge branch and is
    unconditional on echo status -- so an echo-rejected response can have layer2_checked=True
    even though it never reaches a real judge call (the verdict is synthesized, not from
    self._judge.evaluate(...)). reached_judge must stay False regardless of layer2_checked."""
    df = pd.DataFrame(
        [
            {
                "run_id": "run-a",
                "step": "2/10",
                "archetype": "Neutral",
                "bias": "formal",
                "student": "mistral:7b-instruct-q4_K_M",
                "teacher": "qwen:latest",
                "layer0_classification": "VALID",
                "layer1_echo_detected": True,
                "semantic_overlap": 0.91,
                "layer2_checked": True,
                "layer2_predicted_label": "neutral",
                "layer2_contradiction_score": 0.12,
                "v_ok": False,
                "v_confidence": 1.0,
                "rag_enabled": False,
            }
        ]
    )
    row = _build_failure_mode_rows(df)[0]
    assert row["reached_layer1"] is True
    assert row["layer1_result"] == "ECHO"
    assert row["reached_layer2"] is True
    assert row["layer2_result"] == "neutral"
    assert row["reached_judge"] is False, "an echo-rejected response must never be attributed to a real judge call"


def test_build_rows_a_response_that_reaches_a_real_judge_call_is_marked_correctly():
    df = pd.DataFrame(
        [
            {
                "run_id": "run-a",
                "step": "3/10",
                "archetype": "Neutral",
                "bias": "formal",
                "student": "qwen:latest",
                "teacher": "mistral:7b-instruct-q4_K_M",
                "layer0_classification": "VALID",
                "layer1_echo_detected": False,
                "semantic_overlap": 0.15,
                "layer2_checked": False,
                "layer2_predicted_label": None,
                "layer2_contradiction_score": np.nan,
                "v_ok": True,
                "v_confidence": 0.87,
                "rag_enabled": False,
            }
        ]
    )
    row = _build_failure_mode_rows(df)[0]
    assert row["reached_layer1"] is True
    assert row["layer1_result"] == "CLEAN"
    assert row["reached_layer2"] is False
    assert row["reached_judge"] is True
    assert row["judge_result"] == "PASS"
    assert row["teacher"] == "mistral:7b-instruct-q4_K_M"


def test_build_rows_parses_real_rag_chunks_only_when_rag_enabled():
    df = pd.DataFrame(
        [
            {
                "run_id": "run-a",
                "step": "4/10",
                "archetype": "Neutral",
                "bias": "formal",
                "student": "qwen:latest",
                "teacher": "qwen:latest",
                "layer0_classification": "VALID",
                "layer1_echo_detected": False,
                "v_ok": True,
                "v_confidence": 0.9,
                "rag_enabled": True,
                "rag_context": "[baseline | Behavior]\ntext here",
            }
        ]
    )
    row = _build_failure_mode_rows(df)[0]
    assert row["chunks"] == [{"archetype": "baseline", "category": "Behavior"}]

    df.loc[0, "rag_enabled"] = False
    row2 = _build_failure_mode_rows(df)[0]
    assert row2["chunks"] == []


def test_sync_failure_mode_graph_button_sends_the_bootstrap_and_the_unwind_sync(monkeypatch):
    """The new "Sync failure-mode graph" button (distinct from the original "Sync history to
    Neo4j" button, which only ever wrote the plain Archetype-Bias co-occurrence graph) sends two
    real Cypher statements: the one-time CascadeStage/PRECEDES bootstrap, then the per-response
    UNWIND/MERGE sync carrying the resolved cascade-lineage rows."""
    fake_graph = _FakeGraph()
    at = _run_and_click(monkeypatch, fake_graph, button_label="Sync failure-mode graph")

    queries = [c["query"] for c in fake_graph.calls]
    assert any("MERGE (s0:CascadeStage" in q and "PRECEDES" in q for q in queries)
    sync_call = next(c for c in fake_graph.calls if "UNWIND $rows AS row" in c["query"] and "Response" in c["query"])
    assert "MERGE (resp:Response {response_id: row.response_id})" in sync_call["query"]
    assert "REACHED" in sync_call["query"]
    assert len(sync_call["params"]["rows"]) == 2  # _sample_df() has 2 rows
    assert not at.exception
