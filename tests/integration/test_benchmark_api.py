"""
Functional API tests for the Stage 12 read-side endpoints
(:mod:`api.routers.benchmark`) -- through the real FastAPI app, with
``benchmark._repository`` swapped for a fake so no real disk data is
required. Charts/aggregation are built for real against fixture data, not
mocked out.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.benchmark as benchmark
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def _make_run(run_id, started_at, total_tasks=4):
    config = ExperimentConfig(
        student_models=["qwen:latest", "phi3:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["formal"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


def _full_response(student, output, v_ok=True, word_count=42):
    """A response record with every column build_benchmark_view requires, matching a real Stage 6+ entry."""
    return {
        "student": student,
        "teacher": "llama3:latest",
        "archetype": "Detached",
        "bias": "formal",
        "output": output,
        "word_count": word_count,
        "v_ok": v_ok,
        "v_ok_numeric": int(v_ok),
        "ms_per_word": 12.5,
        "duration_ms": 500.0,
        "coherence": 0.6,
        "cognitive_load": 0.4,
        "lexical_density": 0.5,
        "semantic_overlap": 0.3,
        "expansion_ratio": 1.1,
        "self_focus": 0.2,
    }


def _sparse_response():
    """A pre-Stage-5-style response missing most of build_benchmark_view's required columns."""
    return {"student": "qwen:latest", "archetype": "Detached", "bias": "formal", "output": "short output text"}


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo = benchmark._repository
    benchmark._repository = fake_repo
    yield
    benchmark._repository = original_repo


def test_benchmark_page_with_no_runs_shows_empty_state(client):
    """GET /benchmark with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/benchmark")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_benchmark_report_renders_overview_and_leaderboard_for_a_populated_run(client, fake_repo):
    """GET /benchmark/report?run_id=... for a fully-populated run renders overview, charts, and a leaderboard with a champion."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z"))
    fake_repo.save_response("run-a", _full_response("qwen:latest", "response one is here"))
    fake_repo.save_response("run-a", _full_response("qwen:latest", "response two is here"))
    fake_repo.save_response("run-a", _full_response("phi3:latest", "response three is here", v_ok=False))
    fake_repo.save_response("run-a", _full_response("phi3:latest", "response four is here"))

    response = client.get("/benchmark/report", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "Dataset overview" in response.text
    assert "Model leaderboard" in response.text
    assert "Champion" in response.text
    assert "chart-" in response.text


def test_benchmark_report_for_unknown_run_returns_404_with_message(client):
    """GET /benchmark/report?run_id=... for a run with no persisted responses returns 404, matching the other read-side routers' convention."""
    response = client.get("/benchmark/report", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_benchmark_report_degrades_gracefully_on_a_sparse_pre_stage5_run(client, fake_repo):
    """
    Regression coverage mirroring Stage 8's own real-data finding: a run
    missing required columns (student/teacher/word_count/v_ok/...) must
    show a clear message, not 500.
    """
    fake_repo.save_run(_make_run("run-sparse", "2026-08-20T00:00:00Z", total_tasks=1))
    fake_repo.save_response("run-sparse", _sparse_response())

    response = client.get("/benchmark/report", params={"run_id": "run-sparse"})
    assert response.status_code == 200
    assert "not enough data" in response.text.lower()
