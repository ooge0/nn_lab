"""
Functional API tests for :mod:`api.routers.db_export` -- through the real FastAPI app, with
``db_export._repository`` swapped for a fake so no real disk data is required. The target side is
a real temp-file SQLite database (see :mod:`tests.unit.test_db_export`'s docstring for why
``:memory:`` can't exercise the overwrite/collision path) -- ``core.services.db_export`` itself
constructs its own ``SQLiteRepo``, so the test points it at a temp path via monkeypatching the
default rather than mocking SQLite out entirely.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.db_export as db_export_router
import core.services.db_export as db_export_service
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


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original = db_export_router._repository
    db_export_router._repository = fake_repo
    yield
    db_export_router._repository = original


@pytest.fixture(autouse=True)
def _temp_db_path(tmp_path, monkeypatch):
    """Point export_run_to_db's and get_sync_status's default db_path at a real temp file instead
    of the real results/nn_lab.db, so tests never read or write a real on-disk database."""
    target = str(tmp_path / "nn_lab.db")
    original_export = db_export_service.export_run_to_db
    original_status = db_export_service.get_sync_status

    def _patched_export(source_repo, run_id, db_path=target, overwrite=False):
        return original_export(source_repo, run_id, db_path=db_path, overwrite=overwrite)

    def _patched_status(db_path=target):
        return original_status(db_path=db_path)

    monkeypatch.setattr(db_export_router, "export_run_to_db", _patched_export)
    monkeypatch.setattr(db_export_router, "get_sync_status", _patched_status)
    return target


def test_db_export_page_with_no_runs_shows_empty_state(client):
    response = client.get("/db_export")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_db_export_page_lists_runs_with_a_send_to_db_button(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})

    response = client.get("/db_export")

    assert response.status_code == 200
    assert "run-a" in response.text
    assert "Send to DB" in response.text


def test_db_export_page_has_bulk_select_checkboxes_wired_to_each_rows_own_button(client, fake_repo):
    """Bulk export deliberately has no separate backend endpoint -- the 'Send selected to DB'
    button just triggers each checked row's own existing button (htmx.trigger), so per-row
    conflict resolution stays identical to a manual single click. Confirms the wiring is present:
    a select-all checkbox, one checkbox per row carrying its row index, and each row's action
    button having the matching id the bulk-trigger JS looks up."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})
    fake_repo.save_run(_make_run("run-b", "2026-08-21T01:00:00Z"))
    fake_repo.save_response("run-b", {"student": "qwen:latest", "v_ok_numeric": 1})

    response = client.get("/db_export")

    assert response.status_code == 200
    assert 'id="select-all-runs"' in response.text
    assert 'id="export-selected-btn"' in response.text
    assert 'class="run-select" value="run-b"' in response.text or 'class="run-select" value="run-a"' in response.text
    assert 'id="send-to-db-btn-1"' in response.text
    assert 'id="send-to-db-btn-2"' in response.text
    assert "htmx.trigger" in response.text


def test_export_run_copies_responses_and_reports_success(client, fake_repo, _temp_db_path):
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 0})

    response = client.post("/db_export/export", params={"run_id": "run-a"})

    assert response.status_code == 200
    assert "2 response(s)" in response.text
    assert "exported to" in response.text

    from core.adapters.sqlite_repo import SQLiteRepo

    target = SQLiteRepo(db_path=_temp_db_path)
    assert len(target.load_responses("run-a")) == 2


def test_export_run_for_unknown_run_shows_a_clear_error_not_a_500(client):
    response = client.post("/db_export/export", params={"run_id": "never-started"})

    assert response.status_code == 200
    assert "No responses found" in response.text


def test_export_run_twice_without_overwrite_shows_already_exported_with_a_reexport_action(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})
    client.post("/db_export/export", params={"run_id": "run-a"})

    response = client.post("/db_export/export", params={"run_id": "run-a"})

    assert response.status_code == 200
    assert "already has 1 response" in response.text
    assert "Re-export (overwrite)" in response.text


def test_export_run_with_overwrite_true_replaces_rather_than_erroring(client, fake_repo, _temp_db_path):
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})
    client.post("/db_export/export", params={"run_id": "run-a"})

    response = client.post("/db_export/export", params={"run_id": "run-a", "overwrite": "true"})

    assert response.status_code == 200
    assert "1 response(s) re-exported" in response.text


def test_export_failure_for_one_run_does_not_report_success_for_a_different_run(client, fake_repo, _temp_db_path):
    """Two runs visible on the same /db_export page each get their own status fragment
    (id="db-export-result-{run_id}") so htmx swaps the right row -- confirms a failed export for
    one run's response fragment never mentions the other run's id or a stray success badge, which
    would indicate the two rows' results got crossed."""
    fake_repo.save_run(_make_run("run-real", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-real", {"student": "qwen:latest", "v_ok_numeric": 1})
    fake_repo.save_run(_make_run("run-empty", "2026-08-21T01:00:00Z", total_tasks=0))
    # run-empty deliberately gets no save_response call -- a run started but with nothing generated yet.

    ok_response = client.post("/db_export/export", params={"run_id": "run-real"})
    fail_response = client.post("/db_export/export", params={"run_id": "run-empty"})

    assert ok_response.status_code == 200
    assert "db-export-result-run-real" in ok_response.text
    assert "run-empty" not in ok_response.text
    assert "status-ok" in ok_response.text

    assert fail_response.status_code == 200
    assert "db-export-result-run-empty" in fail_response.text
    assert "run-real" not in fail_response.text
    assert "No responses found" in fail_response.text
    assert "status-ok" not in fail_response.text


def test_db_export_page_shows_not_synced_for_a_run_never_exported(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})

    response = client.get("/db_export")

    assert response.status_code == 200
    assert "Export status" in response.text
    assert "Not synced" in response.text


def test_db_export_page_shows_the_real_synced_timestamp_after_an_export(client, fake_repo):
    """Export a run, then reload the page (a fresh GET, simulating a browser refresh) -- the
    'Export status' column must show a real timestamp, not 'Not synced', once the run is actually
    in the database."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})
    client.post("/db_export/export", params={"run_id": "run-a"})

    response = client.get("/db_export")

    assert response.status_code == 200
    assert "UTC" in response.text  # the formatted "YYYY-MM-DD HH:MM:SS UTC" timestamp
    # Only run-a exists, so the page's one non-header "Not synced" occurrence must be gone.
    assert "Not synced" not in response.text


def test_export_run_response_includes_an_out_of_band_update_for_the_sync_status_cell(client, fake_repo):
    """A successful export's response fragment carries an hx-swap-oob element updating the
    'Export status' cell in place, so the new timestamp appears without a page reload."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", {"student": "qwen:latest", "v_ok_numeric": 1})

    response = client.post("/db_export/export", params={"run_id": "run-a"})

    assert response.status_code == 200
    assert 'id="db-export-sync-status-run-a"' in response.text
    assert "hx-swap-oob" in response.text
    assert "UTC" in response.text


def test_export_run_that_fails_does_not_include_a_sync_status_oob_update(client):
    """Nothing actually changed in the database on a failed export -- the OOB fragment (and its
    'Not synced'-vs-timestamp decision) should not be emitted at all, not emitted with a stale or
    fabricated value."""
    response = client.post("/db_export/export", params={"run_id": "never-started"})

    assert response.status_code == 200
    assert "hx-swap-oob" not in response.text
