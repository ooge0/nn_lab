"""
Functional API tests for the Stage 9 read-side endpoints
(:mod:`api.routers.nlp`) -- through the real FastAPI app, with
``nlp._repository`` swapped for a fake so no real disk data is required.
Charts are built for real against fixture data (via the real
``LabDataBridge``), not mocked out.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.nlp as nlp
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def _make_run(run_id, started_at, total_tasks=2):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


def _full_response(student, archetype, bias, val, teacher="llama3:latest"):
    """A response record with the fields LabSchema maps onto Plotly-required columns."""
    return {
        "student": student,
        "teacher": teacher,
        "archetype": archetype,
        "bias": bias,
        "val": val,
        "word_count": 42,
        "readability_ari": 8.5,
        "corrected_ttr": 0.7,
        "subjectivity": 0.4,
        "sentiment": 0.2,
        "lexical_density": 0.5,
        "sentiment_variance": 0.05,
        "repetition_score": 0.3,
        "avg_sentence_length": 12.0,
        "self_focus": 0.1,
        "self_focus_ext": 0.05,
        "rigidity": 0.2,
        "abstract_ratio_ext": 0.1,
        "cognitive_load": 0.6,
        "coherence": 0.4,
        "pos_distribution": {"NOUN": 0.4, "VERB": 0.3, "ADJ": 0.2, "ADV": 0.1},
    }


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo = nlp._repository
    nlp._repository = fake_repo
    yield
    nlp._repository = original_repo


def test_nlp_page_with_no_runs_shows_empty_state(client):
    """GET /nlp with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/nlp")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_nlp_page_renders_all_three_subtabs_for_a_populated_run(client, fake_repo):
    """GET /nlp with a real run renders all three sub-tab headings and real chart HTML."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", _full_response("qwen:latest", "Detached", "formal", 0.2))
    fake_repo.save_response("run-a", _full_response("phi3:latest", "Anxious", "toxic", 0.8))

    response = client.get("/nlp")
    assert response.status_code == 200
    assert "NLP-1" in response.text
    assert "NLP-2" in response.text
    assert "NLP-3" in response.text
    assert "chart-" in response.text


def test_nlp_charts_fragment_for_known_run_returns_populated_charts(client, fake_repo):
    """GET /nlp/charts?run_id=... for a run with responses returns real chart HTML, not the empty state."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", _full_response("qwen:latest", "Detached", "formal", 0.2))
    fake_repo.save_response("run-a", _full_response("phi3:latest", "Anxious", "toxic", 0.8))

    response = client.get("/nlp/charts", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "No responses found" not in response.text
    assert "chart-" in response.text


def test_nlp_charts_fragment_for_unknown_run_returns_404_with_message(client):
    """GET /nlp/charts?run_id=... for a run with no persisted responses returns 404, matching /analytics/charts's convention."""
    response = client.get("/nlp/charts", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_nlp_charts_uses_self_focus_ext_not_self_focus_for_neuro_self_focus(client, fake_repo):
    """
    Regression coverage at the API level for the LabDataBridge fix: a run
    whose responses have deliberately different self_focus (0.9) vs
    self_focus_ext (0.05) must not crash, and must render successfully
    using the corrected mapping (verified at the unit level in
    test_contract.py; this just confirms the whole path from a persisted
    response through to rendered HTML doesn't error).
    """
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    response = _full_response("qwen:latest", "Detached", "formal", 0.2)
    response["self_focus"] = 0.9
    response["self_focus_ext"] = 0.05
    fake_repo.save_response("run-a", response)

    resp = client.get("/nlp/charts", params={"run_id": "run-a"})
    assert resp.status_code == 200
    assert "chart-" in resp.text
