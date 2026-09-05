"""
Functional API tests for the Stage 13 read-side endpoint
(:mod:`api.routers.monitor`) -- through the real FastAPI app, with
``monitor._repository`` swapped for a fake so no real disk data is
required.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.monitor as monitor
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
        biases=["formal"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo = monitor._repository
    monitor._repository = fake_repo
    yield
    monitor._repository = original_repo


def test_monitor_page_with_no_runs_shows_empty_state(client):
    """GET /monitor with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/monitor")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_monitor_schema_reports_correct_dtypes_for_a_populated_run(client, fake_repo):
    """GET /monitor/schema?run_id=... reports the real row/column counts and dtype names for a fixture run."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "word_count": 42, "coherence": 0.5})
    fake_repo.save_response("run-a", {"student": "phi3:latest", "word_count": 10, "coherence": 0.9})

    response = client.get("/monitor/schema", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "2 rows" in response.text
    assert "3 columns" in response.text
    assert "word_count" in response.text
    assert "int64" in response.text
    assert "coherence" in response.text
    assert "float64" in response.text


def test_monitor_schema_for_unknown_run_returns_404_with_message(client):
    """GET /monitor/schema?run_id=... for a run with no persisted responses returns 404, matching the other read-side routers' convention."""
    response = client.get("/monitor/schema", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_monitor_schema_includes_a_data_preview_table(client, fake_repo):
    """GET /monitor/schema?run_id=... includes a rendered preview table with real cell values, not just the dtypes."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "archetype": "Detached"})

    response = client.get("/monitor/schema", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "Data preview" in response.text
    assert "qwen:latest" in response.text
    assert "Detached" in response.text


def test_monitor_schema_default_view_truncates_to_20_rows_with_a_show_all_link(client, fake_repo):
    """
    Regression test for the "view JSONL as a table" gap: by default only
    the first 20 rows render, but a real "Show all N rows" link to
    ?full=true is present so every row is genuinely reachable, not just
    the preview -- the direct replacement for the legacy Streamlit app's
    full-table view.
    """
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z", total_tasks=25))
    for i in range(25):
        fake_repo.save_response("run-a", {"student": "qwen:latest", "step": i})

    response = client.get("/monitor/schema", params={"run_id": "run-a"})

    assert response.status_code == 200
    assert "25 rows" in response.text
    assert response.text.count("<tr>") <= 22  # header row + <=20 data rows + slack, not all 25
    assert "full=true" in response.text
    assert "Show all 25 rows" in response.text


def test_monitor_schema_full_true_returns_every_row(client, fake_repo):
    """GET /monitor/schema?run_id=...&full=true returns all 25 rows, not just the 20-row preview."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z", total_tasks=25))
    for i in range(25):
        fake_repo.save_response("run-a", {"student": "qwen:latest", "step": i})

    response = client.get("/monitor/schema", params={"run_id": "run-a", "full": "true"})

    assert response.status_code == 200
    for i in range(25):
        assert f">{i}<" in response.text  # every step value 0..24 present as a real cell
    assert "Show first 20 rows only" in response.text
