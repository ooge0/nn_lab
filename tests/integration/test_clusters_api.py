"""
Functional API tests for the Stage 10 read-side endpoints
(:mod:`api.routers.clusters`) -- through the real FastAPI app, with
``clusters._repository`` swapped for a fake so no real disk data is
required. Kept to a small number of full-clustering tests deliberately --
UMAP/HDBSCAN fitting takes real seconds even on synthetic data, and the
computation itself is already thoroughly covered by
``tests/unit/test_cluster_discovery.py``'s unit tests. These tests confirm
routing/wiring, not re-verify the algorithms.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.routers.clusters as clusters
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def _make_run(run_id, started_at, total_tasks=20):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


def _synthetic_response(i, rng):
    return {
        "student": ["qwen:latest", "phi3:latest"][i % 2],
        "teacher": "llama3:latest",
        "archetype": ["Detached", "Anxious"][i % 2],
        "bias": "formal",
        "val": float(rng.random()),
        "v_ok": True,
        "v_ok_numeric": 1,
        "output": "a synthetic response with enough words in it to reliably pass the default fifteen word minimum length filter used by behavioral topology",
        "sentiment": float(rng.standard_normal()),
        "subjectivity": float(rng.random()),
        "rigidity": float(rng.standard_normal()),
        "modality": float(rng.random()),
        "cognitive_density": float(rng.random()),
        "cognitive_load": float(rng.random()),
        "coherence": float(rng.random()),
        "abstract_ratio": float(rng.random()),
        "semantic_overlap": float(rng.random()),
        "lexical_density": float(rng.random()),
        "corrected_ttr": float(rng.random()),
        "avg_sentence_length": float(rng.integers(5, 20)),
        "word_count": int(rng.integers(10, 100)),
        "readability_ari": float(rng.random() * 15),
        "unique_ratio": float(rng.random()),
        "repetition_score": float(rng.random()),
        "punc_density": float(rng.random()),
        "zipf_deviation": float(rng.random()),
    }


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo = clusters._repository
    clusters._repository = fake_repo
    yield
    clusters._repository = original_repo


def test_clusters_page_with_no_runs_shows_empty_state(client):
    """GET /clusters with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/clusters")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_clusters_charts_fragment_for_unknown_run_returns_404_with_message(client):
    """GET /clusters/charts?run_id=... for a run with no persisted responses returns 404, matching /analytics/charts's convention."""
    response = client.get("/clusters/charts", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_clusters_charts_degrades_gracefully_with_too_few_responses(client, fake_repo):
    """A run with only a couple of responses (below every clustering algorithm's minimum) renders the graceful 'not enough data' messages, not a 500."""
    fake_repo.save_run(_make_run("run-small", "2026-08-21T00:00:00Z", total_tasks=2))
    rng = np.random.default_rng(1)
    fake_repo.save_response("run-small", _synthetic_response(0, rng))
    fake_repo.save_response("run-small", _synthetic_response(1, rng))

    response = client.get("/clusters/charts", params={"run_id": "run-small"})
    assert response.status_code == 200
    assert "Not enough data points" in response.text


def test_clusters_page_renders_all_three_subtabs_for_a_populated_run(client, fake_repo):
    """GET /clusters with enough real data renders K-Means, HDBSCAN, and Behavioral topology charts -- the one full end-to-end run through the whole pipeline."""
    fake_repo.save_run(_make_run("run-full", "2026-08-21T00:00:00Z"))
    rng = np.random.default_rng(42)
    for i in range(25):
        fake_repo.save_response("run-full", _synthetic_response(i, rng))

    response = client.get("/clusters")
    assert response.status_code == 200
    assert "K-Means (PCA)" in response.text
    assert "HDBSCAN (Density)" in response.text
    assert "Behavioral topology" in response.text
    assert "chart-" in response.text
    assert "Silhouette" in response.text
