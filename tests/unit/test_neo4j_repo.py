"""
Unit tests for :mod:`core.adapters.neo4j_repo` -- the ``GraphRepository`` implementation promoted
2026-09-05 from the legacy Neo4j subsystem into the layered architecture (see
:class:`core.domain.interfaces.GraphRepository`'s own docstring for the exact scope of that
decision). No live Neo4j server, no Docker (this project has neither, by design) -- a fake,
in-memory stand-in for ``py2neo.Graph`` records every Cypher string + params sent, in order, and
returns query-shape-appropriate canned data. This checks query construction/ordering and the
row-building logic, not that a real Neo4j+GDS deployment works -- that was verified manually, once,
for real, driving the actual FastAPI app against a live Neo4j install (see
``docs/source/wiki/07-knowledge-graph-results.rst``).
"""

from core.adapters.neo4j_repo import Neo4jGraphRepo, _build_failure_mode_rows, _parse_rag_chunks


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def data(self):
        return self._rows


class _FakeGraph:
    def __init__(self):
        self.calls: list[dict] = []

    def run(self, query, **params):
        self.calls.append({"query": query, "params": params})
        q = " ".join(query.split())
        if "GENERATED_BY" in q and "echo_count" in q:
            return _FakeResult([{"model": "mistral", "echo_count": 27}, {"model": "qwen", "echo_count": 12}])
        if "terminal_stage" in q:
            return _FakeResult([{"terminal_stage": "Judge", "terminal_result": "PASS", "n": 47}])
        if "chunk_archetype" in q:
            return _FakeResult([{"chunk_archetype": "paranoid", "chunk_category": "Behavior", "echo_count": 36}])
        return _FakeResult()


# --- _parse_rag_chunks -----------------------------------------------------------------------


def test_parse_rag_chunks_recovers_archetype_and_category_from_the_real_serialized_format():
    ctx = "[baseline | Behavior]\nSome behavior text.\n\n[paranoid | Speech]\nSome speech text."
    assert _parse_rag_chunks(ctx) == [
        {"archetype": "baseline", "category": "Behavior"},
        {"archetype": "paranoid", "category": "Speech"},
    ]


def test_parse_rag_chunks_handles_empty_and_none_input():
    assert _parse_rag_chunks("") == []
    assert _parse_rag_chunks(None) == []


# --- _build_failure_mode_rows (plain dict, no pandas) -----------------------------------------


def test_build_rows_layer0_rejected_response_reaches_nothing_past_layer0():
    responses = [
        {
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
    row = _build_failure_mode_rows(responses, run_id="run-a")[0]
    assert row["response_id"] == "run-a:1/10"
    assert row["layer0_classification"] == "TRUNCATED"
    assert row["reached_layer1"] is False
    assert row["reached_layer2"] is False
    assert row["reached_judge"] is False
    assert row["chunks"] == []


def test_build_rows_echo_rejected_response_can_still_reach_layer2_but_never_the_judge():
    """Real, non-obvious pipeline behavior: Layer 2's hallucination check runs unconditionally on
    echo status, so an echo-rejected response can have layer2_checked=True even though it never
    reaches a real judge call -- reached_judge must stay False regardless."""
    responses = [
        {
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
    row = _build_failure_mode_rows(responses, run_id="run-a")[0]
    assert row["reached_layer1"] is True
    assert row["layer1_result"] == "ECHO"
    assert row["reached_layer2"] is True
    assert row["reached_judge"] is False, "an echo-rejected response must never be attributed to a real judge call"


def test_build_rows_a_response_that_reaches_a_real_judge_call_is_marked_correctly():
    responses = [
        {
            "step": "3/10",
            "archetype": "Neutral",
            "bias": "formal",
            "student": "qwen:latest",
            "teacher": "mistral:7b-instruct-q4_K_M",
            "layer0_classification": "VALID",
            "layer1_echo_detected": False,
            "semantic_overlap": 0.15,
            "v_ok": True,
            "v_confidence": 0.87,
            "rag_enabled": False,
        }
    ]
    row = _build_failure_mode_rows(responses, run_id="run-a")[0]
    assert row["reached_layer1"] is True
    assert row["reached_layer2"] is False
    assert row["reached_judge"] is True
    assert row["judge_result"] == "PASS"
    assert row["teacher"] == "mistral:7b-instruct-q4_K_M"


def test_build_rows_parses_real_rag_chunks_only_when_rag_enabled():
    base = {
        "step": "4/10",
        "archetype": "Neutral",
        "bias": "formal",
        "student": "qwen:latest",
        "teacher": "qwen:latest",
        "layer0_classification": "VALID",
        "layer1_echo_detected": False,
        "v_ok": True,
        "v_confidence": 0.9,
        "rag_context": "[baseline | Behavior]\ntext here",
    }
    with_rag = {**base, "rag_enabled": True}
    without_rag = {**base, "rag_enabled": False}
    assert _build_failure_mode_rows([with_rag], run_id="run-a")[0]["chunks"] == [
        {"archetype": "baseline", "category": "Behavior"}
    ]
    assert _build_failure_mode_rows([without_rag], run_id="run-a")[0]["chunks"] == []


# --- Neo4jGraphRepo ----------------------------------------------------------------------------


def test_sync_sends_the_bootstrap_and_the_unwind_sync_and_returns_the_real_count():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)
    responses = [
        {
            "step": "1/2",
            "archetype": "A",
            "bias": "b",
            "student": "s",
            "teacher": "t",
            "layer0_classification": "VALID",
            "layer1_echo_detected": False,
            "v_ok": True,
            "v_confidence": 0.9,
        },
        {
            "step": "2/2",
            "archetype": "A",
            "bias": "b",
            "student": "s",
            "teacher": "t",
            "layer0_classification": "TRUNCATED",
            "layer1_echo_detected": False,
            "v_ok": False,
            "v_confidence": 1.0,
        },
    ]

    count = repo.sync_failure_mode_graph("run-a", responses)

    assert count == 2
    queries = [c["query"] for c in fake_graph.calls]
    assert any("MERGE (s0:CascadeStage" in q and "PRECEDES" in q for q in queries)
    sync_call = next(c for c in fake_graph.calls if "UNWIND $rows AS row" in c["query"])
    assert len(sync_call["params"]["rows"]) == 2
    assert sync_call["params"]["rows"][0]["run_id"] == "run-a"


def test_sync_with_zero_responses_does_not_send_the_unwind_query_and_returns_zero():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)
    count = repo.sync_failure_mode_graph("run-a", [])
    assert count == 0
    assert not any("UNWIND $rows AS row" in c["query"] for c in fake_graph.calls)


def test_echo_rejections_by_model_returns_the_real_query_shape():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)
    rows = repo.echo_rejections_by_model()
    assert rows == [{"model": "mistral", "echo_count": 27}, {"model": "qwen", "echo_count": 12}]


def test_terminal_stage_by_archetype_passes_the_archetype_param():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)
    rows = repo.terminal_stage_by_archetype("Defensive")
    assert rows == [{"terminal_stage": "Judge", "terminal_result": "PASS", "n": 47}]
    assert fake_graph.calls[0]["params"] == {"archetype": "Defensive"}


def test_rag_chunks_linked_to_echo_returns_the_real_query_shape():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)
    rows = repo.rag_chunks_linked_to_echo()
    assert rows == [{"chunk_archetype": "paranoid", "chunk_category": "Behavior", "echo_count": 36}]
