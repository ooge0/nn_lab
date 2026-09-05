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

from core.adapters.neo4j_repo import (
    Neo4jGraphRepo,
    _build_failure_mode_rows,
    _parse_rag_chunks,
    _summarize_similarity_pairs,
)


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
        if "gds.leiden.stats" in q:
            return _FakeResult([{"community_count": 2, "modularity": 0.42}])
        if "gds.leiden.stream" in q:
            return _FakeResult(
                [
                    {"community_id": 0, "node_type": "Archetype", "name": "Detached"},
                    {"community_id": 0, "node_type": "Model", "name": "qwen:latest"},
                    {"community_id": 1, "node_type": "Archetype", "name": "Defensive"},
                ]
            )
        if "gds.knn.stream" in q:
            return _FakeResult(
                [
                    {
                        "node_a_type": "Archetype",
                        "node_a_name": "Detached",
                        "node_b_type": "Archetype",
                        "node_b_name": "Neutral",
                        "similarity": 0.99,
                    },
                    {
                        "node_a_type": "Bias",
                        "node_a_name": "personalization",
                        "node_b_type": "Archetype",
                        "node_b_name": "Detached",
                        "similarity": 0.0,
                    },
                ]
            )
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


# --- _summarize_similarity_pairs (Stage 5) ------------------------------------------------------


def test_summarize_similarity_pairs_dedupes_directed_rows_keeping_the_max_similarity():
    """gds.knn.stream returns each real-world pair twice (once from each node's own top-K list),
    with slightly different scores possible -- must collapse to one row, keeping the higher score."""
    raw = [
        {
            "node_a_type": "Model",
            "node_a_name": "qwen:latest",
            "node_b_type": "Model",
            "node_b_name": "tinyllama:latest",
            "similarity": 0.91,
        },
        {
            "node_a_type": "Model",
            "node_a_name": "tinyllama:latest",
            "node_b_type": "Model",
            "node_b_name": "qwen:latest",
            "similarity": 0.93,
        },
    ]
    result = _summarize_similarity_pairs(raw)
    assert result["top_similar_pairs"] == [
        {
            "node_a_type": "Model",
            "node_a_name": "tinyllama:latest",
            "node_b_type": "Model",
            "node_b_name": "qwen:latest",
            "similarity": 0.93,
        }
    ]


def test_summarize_similarity_pairs_excludes_self_pairs():
    raw = [
        {
            "node_a_type": "Archetype",
            "node_a_name": "Detached",
            "node_b_type": "Archetype",
            "node_b_name": "Detached",
            "similarity": 1.0,
        }
    ]
    result = _summarize_similarity_pairs(raw)
    assert result["top_similar_pairs"] == []
    assert result["most_anomalous"] is None


def test_summarize_similarity_pairs_caps_at_five_sorted_descending():
    raw = [
        {
            "node_a_type": "Archetype",
            "node_a_name": f"A{i}",
            "node_b_type": "Archetype",
            "node_b_name": f"B{i}",
            "similarity": i / 10,
        }
        for i in range(8)
    ]
    result = _summarize_similarity_pairs(raw)
    scores = [p["similarity"] for p in result["top_similar_pairs"]]
    assert len(scores) == 5
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 0.7


def test_summarize_similarity_pairs_flags_the_node_whose_best_match_is_weakest_as_anomalous():
    """Real Stage 5 finding, not invented: a node can have a merely-ordinary similarity to one
    neighbor while its overall *best* match is still far weaker than every other node's best
    match -- that's the real anomaly signal, not just "the lowest number that appears anywhere"."""
    raw = [
        {
            "node_a_type": "Archetype",
            "node_a_name": "Detached",
            "node_b_type": "Archetype",
            "node_b_name": "Neutral",
            "similarity": 0.99,
        },
        {
            "node_a_type": "Bias",
            "node_a_name": "personalization",
            "node_b_type": "Archetype",
            "node_b_name": "Detached",
            "similarity": 0.0,
        },
    ]
    result = _summarize_similarity_pairs(raw)
    assert result["most_anomalous"] == {"node_type": "Bias", "name": "personalization", "best_similarity": 0.0}


def test_summarize_similarity_pairs_handles_empty_input():
    result = _summarize_similarity_pairs([])
    assert result == {"top_similar_pairs": [], "most_anomalous": None}


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


# --- behavioral_communities (Stage 4, docs/source/wiki/08-graph-representation-learning.rst) ---


def test_behavioral_communities_returns_modularity_count_and_rows():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    result = repo.behavioral_communities()

    assert result["community_count"] == 2
    assert result["modularity"] == 0.42
    assert result["rows"] == [
        {"community_id": 0, "node_type": "Archetype", "name": "Detached"},
        {"community_id": 0, "node_type": "Model", "name": "qwen:latest"},
        {"community_id": 1, "node_type": "Archetype", "name": "Defensive"},
    ]


def test_behavioral_communities_materializes_cooccurrence_then_projects_before_running_leiden():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    repo.behavioral_communities()

    queries = [c["query"] for c in fake_graph.calls]
    assert any("CO_OCCURS_WITH" in q and "MERGE" in q for q in queries)
    assert any("gds.graph.project" in q for q in queries)
    cooccur_idx = next(i for i, q in enumerate(queries) if "CO_OCCURS_WITH" in q and "MERGE" in q)
    project_idx = next(i for i, q in enumerate(queries) if "gds.graph.project" in q)
    leiden_idx = next(i for i, q in enumerate(queries) if "gds.leiden.stats" in q)
    assert cooccur_idx < project_idx < leiden_idx, "must materialize co-occurrence, then project, then run Leiden"


def test_behavioral_communities_drops_the_projected_graph_both_before_and_after():
    """Real GDS behavior: a stale in-memory graph catalog entry from a previous call would make a
    second gds.graph.project call fail outright -- drop-if-exists must run before projecting, and
    the projection must not leak GDS catalog memory across calls (a real, disclosed limitation --
    see docs/source/wiki/07-knowledge-graph-results.rst), so it must also be dropped after use."""
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    repo.behavioral_communities()

    drop_calls = [c for c in fake_graph.calls if "gds.graph.drop" in c["query"]]
    assert len(drop_calls) == 2, "must drop before projecting (stale catalog) and after (no leaked memory)"
    for c in drop_calls:
        assert c["params"] == {"graph_name": "behavioral-communities"}


def test_behavioral_communities_still_drops_the_graph_when_leiden_itself_raises():
    class _RaisingGraph(_FakeGraph):
        def run(self, query, **params):
            q = " ".join(query.split())
            if "gds.leiden.stats" in q:
                raise RuntimeError("GDS out of memory")
            return super().run(query, **params)

    fake_graph = _RaisingGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    try:
        repo.behavioral_communities()
        assert False, "expected the RuntimeError to propagate"
    except RuntimeError:
        pass

    drop_calls = [c for c in fake_graph.calls if "gds.graph.drop" in c["query"]]
    assert len(drop_calls) == 2, "the projected graph must still be dropped even when Leiden itself fails"


# --- Neo4jGraphRepo.structural_similarity (Stage 5) ---------------------------------------------


def test_structural_similarity_returns_the_summarized_shape():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    result = repo.structural_similarity()

    assert result["most_anomalous"] == {"node_type": "Bias", "name": "personalization", "best_similarity": 0.0}
    assert result["top_similar_pairs"] == [
        {
            "node_a_type": "Archetype",
            "node_a_name": "Detached",
            "node_b_type": "Archetype",
            "node_b_name": "Neutral",
            "similarity": 0.99,
        },
        {
            "node_a_type": "Bias",
            "node_a_name": "personalization",
            "node_b_type": "Archetype",
            "node_b_name": "Detached",
            "similarity": 0.0,
        },
    ]


def test_structural_similarity_mutates_embeddings_before_running_knn():
    fake_graph = _FakeGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    repo.structural_similarity()

    queries = [c["query"] for c in fake_graph.calls]
    mutate_idx = next(i for i, q in enumerate(queries) if "gds.fastRP.mutate" in q)
    knn_idx = next(i for i, q in enumerate(queries) if "gds.knn.stream" in q)
    assert mutate_idx < knn_idx, "embeddings must be written before gds.knn can consume them"


def test_structural_similarity_still_drops_the_graph_when_knn_itself_raises():
    class _RaisingGraph(_FakeGraph):
        def run(self, query, **params):
            q = " ".join(query.split())
            if "gds.knn.stream" in q:
                raise RuntimeError("GDS out of memory")
            return super().run(query, **params)

    fake_graph = _RaisingGraph()
    repo = Neo4jGraphRepo(graph=fake_graph)

    try:
        repo.structural_similarity()
        assert False, "expected the RuntimeError to propagate"
    except RuntimeError:
        pass

    drop_calls = [c for c in fake_graph.calls if "gds.graph.drop" in c["query"]]
    assert len(drop_calls) == 2, "the projected graph must still be dropped even when KNN itself fails"
