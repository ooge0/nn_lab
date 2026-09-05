"""
Functional API tests for the Stage 7 read-side endpoints
(:mod:`api.routers.runs`) -- through the real FastAPI app, with
``runs._repository``/``runs._metrics_engine`` swapped for fakes so no real
disk data is required.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.runs as runs
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from core.services.metrics_engine import MetricsEngine
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


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo, original_engine = runs._repository, runs._metrics_engine
    runs._repository = fake_repo
    runs._metrics_engine = MetricsEngine(fake_repo)
    yield
    runs._repository, runs._metrics_engine = original_repo, original_engine


def test_runs_page_with_no_runs_shows_empty_state(client):
    """GET /runs with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/runs")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_runs_page_selects_most_recently_started_run_by_default(client, fake_repo):
    """GET /runs with multiple runs pre-selects the one with the latest started_at and shows its summary."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "val": 0.2, "step": 1, "duration_ms": 100.0})
    fake_repo.save_run(_make_run("run-b", "2026-08-21T01:00:00Z"))
    fake_repo.save_response("run-b", {"student": "qwen:latest", "val": 0.5, "step": 1, "duration_ms": 200.0})

    response = client.get("/runs")
    assert response.status_code == 200
    assert 'value="run-b" selected' in response.text
    assert "Total records" in response.text


def test_run_summary_fragment_for_known_run_returns_populated_table(client, fake_repo):
    """GET /runs/summary?run_id=... for a run with responses returns the populated summary fragment."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "val": 0.2, "step": 1, "duration_ms": 100.0})

    response = client.get("/runs/summary", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "Total records" in response.text
    assert "1" in response.text


def test_run_summary_fragment_for_unknown_run_returns_404_with_message(client):
    """GET /runs/summary?run_id=... for a run with no persisted responses returns 404, not a 500 or an empty table."""
    response = client.get("/runs/summary", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text or "never-started" in response.text


def test_runs_page_renders_the_judging_comparison_picker(client, fake_repo):
    """GET /runs with runs present shows the self-critic-vs-teacher-judging comparison form."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "val": 0.2, "step": 1, "duration_ms": 100.0})

    response = client.get("/runs")
    assert response.status_code == 200
    assert "Self-critic vs. teacher-judging comparison" in response.text
    assert 'name="run_id_a"' in response.text
    assert 'name="run_id_b"' in response.text


def test_judging_comparison_fragment_shows_pass_rates_and_delta(client, fake_repo):
    """GET /runs/judging_comparison for a self-critic run and a teacher-judged run renders both
    pass rates, both mode labels, and the delta -- a real end-to-end check of the router wiring, not
    just the underlying MetricsEngine call (already unit-pinned separately)."""
    self_critic_config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model=None,
        self_critic=True,
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    fake_repo.save_run(
        RunRecord(run_id="run-self", started_at="2026-08-21T00:00:00Z", config=self_critic_config, total_tasks=1)
    )
    fake_repo.save_response("run-self", {"word_count": 10, "v_ok_numeric": 1})
    fake_repo.save_run(_make_run("run-teacher", "2026-08-21T01:00:00Z"))
    fake_repo.save_response("run-teacher", {"word_count": 10, "v_ok_numeric": 0})

    response = client.get("/runs/judging_comparison", params={"run_id_a": "run-self", "run_id_b": "run-teacher"})

    assert response.status_code == 200
    assert "Self-critic (judge = student itself)" in response.text
    assert "Teacher-judged (llama3:latest)" in response.text
    assert "100.0%" in response.text
    assert "0.0%" in response.text
    assert "+100.0 pp" in response.text


def test_judging_comparison_fragment_for_unknown_run_returns_404_with_message(client, fake_repo):
    """GET /runs/judging_comparison where one run_id has no persisted responses returns 404, not a 500."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"word_count": 10, "v_ok_numeric": 1})

    response = client.get("/runs/judging_comparison", params={"run_id_a": "run-a", "run_id_b": "never-started"})

    assert response.status_code == 404
    assert "never-started" in response.text
