"""
Functional API tests for :mod:`api.routers.knowledge_graph` -- through the real FastAPI app, with
both ``knowledge_graph._repository`` and ``knowledge_graph._graph_repo`` swapped for fakes so no
real disk data or live Neo4j server is required. Real Neo4j+GDS behavior was verified manually,
once, driving this exact router against a live install -- see
``docs/source/wiki/07-knowledge-graph-results.rst``.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.knowledge_graph as kg_router
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class _FakeGraphRepo:
    """Records calls, returns canned data -- no live Neo4j needed."""

    def __init__(self):
        self.synced: list[tuple] = []
        self.echo_by_model_result = [{"model": "mistral", "echo_count": 27}, {"model": "qwen", "echo_count": 12}]
        self.terminal_stage_result = [{"terminal_stage": "Judge", "terminal_result": "PASS", "n": 47}]
        self.rag_chunks_result = [{"chunk_archetype": "paranoid", "chunk_category": "Behavior", "echo_count": 36}]
        self.behavioral_communities_result = {
            "modularity": 0.42,
            "community_count": 2,
            "rows": [
                {"community_id": 0, "node_type": "Archetype", "name": "Detached"},
                {"community_id": 0, "node_type": "Model", "name": "qwen:latest"},
                {"community_id": 1, "node_type": "Archetype", "name": "Defensive"},
            ],
        }
        self.structural_similarity_result = {
            "top_similar_pairs": [
                {
                    "node_a_type": "Archetype",
                    "node_a_name": "Detached",
                    "node_b_type": "Archetype",
                    "node_b_name": "Neutral",
                    "similarity": 0.9999,
                }
            ],
            "most_anomalous": {"node_type": "Bias", "name": "personalization", "best_similarity": 0.0},
        }
        self.raise_on_query = False

    def sync_failure_mode_graph(self, run_id, responses):
        if self.raise_on_query:
            raise RuntimeError("Cannot open connection to bolt://localhost:7687")
        self.synced.append((run_id, len(responses)))
        return len(responses)

    def echo_rejections_by_model(self):
        if self.raise_on_query:
            raise RuntimeError("Cannot open connection to bolt://localhost:7687")
        return self.echo_by_model_result

    def terminal_stage_by_archetype(self, archetype):
        if self.raise_on_query:
            raise RuntimeError("Cannot open connection to bolt://localhost:7687")
        return self.terminal_stage_result

    def rag_chunks_linked_to_echo(self):
        if self.raise_on_query:
            raise RuntimeError("Cannot open connection to bolt://localhost:7687")
        return self.rag_chunks_result

    def behavioral_communities(self):
        if self.raise_on_query:
            raise RuntimeError("Cannot open connection to bolt://localhost:7687")
        return self.behavioral_communities_result

    def structural_similarity(self):
        if self.raise_on_query:
            raise RuntimeError("Cannot open connection to bolt://localhost:7687")
        return self.structural_similarity_result


def _make_run(run_id, started_at, total_tasks=2):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture
def fake_graph_repo():
    return _FakeGraphRepo()


@pytest.fixture(autouse=True)
def _fakes(fake_repo, fake_graph_repo):
    orig_repo = kg_router._repository
    orig_graph = kg_router._graph_repo
    kg_router._repository = fake_repo
    kg_router._graph_repo = fake_graph_repo
    yield
    kg_router._repository = orig_repo
    kg_router._graph_repo = orig_graph


def test_page_with_no_runs_shows_empty_state(client):
    response = client.get("/knowledge_graph")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_page_with_a_run_lists_it_and_its_archetypes(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    fake_repo.save_response("run-a", {"archetype": "Detached", "bias": "toxic"})
    fake_repo.save_response("run-a", {"archetype": "Neutral", "bias": "formal"})

    response = client.get("/knowledge_graph")
    assert response.status_code == 200
    assert "run-a" in response.text
    assert "Detached" in response.text
    assert "Neutral" in response.text


def test_sync_calls_the_graph_repo_with_the_real_run_id_and_responses(client, fake_repo, fake_graph_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    fake_repo.save_response("run-a", {"archetype": "Detached", "bias": "toxic"})

    response = client.post("/knowledge_graph/sync", params={"run_id": "run-a"})

    assert response.status_code == 200
    assert "synced" in response.text
    assert fake_graph_repo.synced == [("run-a", 1)]


def test_sync_for_a_run_with_no_responses_shows_a_clear_error_not_a_500(client):
    response = client.post("/knowledge_graph/sync", params={"run_id": "unknown-run"})
    assert response.status_code == 200
    assert "No responses found" in response.text


def test_sync_when_neo4j_is_unreachable_shows_a_clear_error_not_a_500(client, fake_repo, fake_graph_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    fake_repo.save_response("run-a", {"archetype": "Detached", "bias": "toxic"})
    fake_graph_repo.raise_on_query = True

    response = client.post("/knowledge_graph/sync", params={"run_id": "run-a"})

    assert response.status_code == 200
    assert "Error syncing failure-mode graph" in response.text


def test_echo_by_model_renders_the_real_query_result(client):
    response = client.get("/knowledge_graph/echo_by_model")
    assert response.status_code == 200
    assert "mistral" in response.text and "27" in response.text
    assert "qwen" in response.text and "12" in response.text


def test_terminal_stage_passes_the_archetype_and_renders_the_result(client, fake_graph_repo):
    response = client.get("/knowledge_graph/terminal_stage", params={"archetype": "Defensive"})
    assert response.status_code == 200
    assert "Defensive" in response.text
    assert "Judge" in response.text and "PASS" in response.text


def test_rag_chunks_echo_renders_the_real_query_result(client):
    response = client.get("/knowledge_graph/rag_chunks_echo")
    assert response.status_code == 200
    assert "paranoid" in response.text and "Behavior" in response.text and "36" in response.text


def test_query_when_neo4j_is_unreachable_shows_a_clear_error_not_a_500(client, fake_graph_repo):
    fake_graph_repo.raise_on_query = True
    response = client.get("/knowledge_graph/echo_by_model")
    assert response.status_code == 200
    assert "Error running query" in response.text


def test_behavioral_communities_renders_modularity_and_the_community_rows(client):
    response = client.get("/knowledge_graph/behavioral_communities")
    assert response.status_code == 200
    assert "0.4200" in response.text
    assert "Detached" in response.text and "qwen:latest" in response.text and "Defensive" in response.text


def test_behavioral_communities_when_neo4j_is_unreachable_shows_a_clear_error_not_a_500(client, fake_graph_repo):
    fake_graph_repo.raise_on_query = True
    response = client.get("/knowledge_graph/behavioral_communities")
    assert response.status_code == 200
    assert "Error running query" in response.text


def test_structural_similarity_renders_the_top_pairs_and_the_anomaly(client):
    response = client.get("/knowledge_graph/structural_similarity")
    assert response.status_code == 200
    assert "Detached" in response.text and "Neutral" in response.text
    assert "personalization" in response.text
    assert "0.0000" in response.text


def test_structural_similarity_when_neo4j_is_unreachable_shows_a_clear_error_not_a_500(client, fake_graph_repo):
    fake_graph_repo.raise_on_query = True
    response = client.get("/knowledge_graph/structural_similarity")
    assert response.status_code == 200
    assert "Error running query" in response.text
