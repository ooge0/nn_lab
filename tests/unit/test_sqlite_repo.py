"""
Unit tests for :class:`core.adapters.sqlite_repo.SQLiteRepo` -- CRUD against
an in-memory SQLite database (``:memory:``, no file left behind).
"""

from core.adapters.sqlite_repo import SQLiteRepo
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord


def _make_run(run_id="run-1"):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="qwen:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at="2026-08-21T00:00:00Z", config=config, total_tasks=2)


def test_save_run_returns_the_run_id():
    """save_run() echoes the run's own ID back."""
    repo = SQLiteRepo(db_path=":memory:")
    assert repo.save_run(_make_run("run-1")) == "run-1"


def test_save_run_persists_config_as_structured_data():
    """A saved run's config round-trips through the ORM's JSON column intact."""
    repo = SQLiteRepo(db_path=":memory:")
    run = _make_run()
    repo.save_run(run)

    with repo._session_factory() as session:
        from core.adapters.sqlite_repo import RunORM

        row = session.get(RunORM, "run-1")
        assert row.total_tasks == 2
        assert row.config_json["student_models"] == ["qwen:latest"]
        assert row.config_json["prompt_mode"] == "Behavioral conditioning (Tuned)"


def test_save_response_and_load_responses_round_trip():
    """Responses saved for a run come back identical via load_responses(run_id)."""
    repo = SQLiteRepo(db_path=":memory:")
    run = _make_run()
    repo.save_run(run)
    repo.save_response(run.run_id, {"student": "qwen:latest", "v_ok": True})
    repo.save_response(run.run_id, {"student": "phi3:latest", "v_ok": False})

    loaded = repo.load_responses(run.run_id)
    assert loaded == [
        {"student": "qwen:latest", "v_ok": True},
        {"student": "phi3:latest", "v_ok": False},
    ]


def test_load_responses_filters_by_run_id_across_multiple_runs():
    """load_responses(run_id) does not leak another run's responses -- the normalization Stage 0's finding motivated."""
    repo = SQLiteRepo(db_path=":memory:")
    run_a, run_b = _make_run("run-a"), _make_run("run-b")
    repo.save_run(run_a)
    repo.save_run(run_b)
    repo.save_response(run_a.run_id, {"student": "a"})
    repo.save_response(run_b.run_id, {"student": "b"})

    assert repo.load_responses(run_a.run_id) == [{"student": "a"}]
    assert repo.load_responses(run_b.run_id) == [{"student": "b"}]


def test_load_responses_without_run_id_returns_all_runs():
    """load_responses() with no run_id returns responses across every run."""
    repo = SQLiteRepo(db_path=":memory:")
    run_a, run_b = _make_run("run-a"), _make_run("run-b")
    repo.save_run(run_a)
    repo.save_run(run_b)
    repo.save_response(run_a.run_id, {"student": "a"})
    repo.save_response(run_b.run_id, {"student": "b"})

    assert len(repo.load_responses()) == 2


def test_delete_responses_removes_only_the_target_runs_rows_and_returns_the_count():
    """delete_responses(run_id) clears one run's rows, leaves other runs' rows untouched, and
    reports how many were removed -- the mechanism export_run_to_db's overwrite path relies on."""
    repo = SQLiteRepo(db_path=":memory:")
    run_a, run_b = _make_run("run-a"), _make_run("run-b")
    repo.save_run(run_a)
    repo.save_run(run_b)
    repo.save_response(run_a.run_id, {"student": "a1"})
    repo.save_response(run_a.run_id, {"student": "a2"})
    repo.save_response(run_b.run_id, {"student": "b1"})

    deleted = repo.delete_responses("run-a")

    assert deleted == 2
    assert repo.load_responses("run-a") == []
    assert repo.load_responses("run-b") == [{"student": "b1"}]


def test_save_run_twice_with_same_id_upserts_rather_than_duplicating():
    """Saving a run with an already-used run_id updates it in place (merge), not a duplicate row."""
    repo = SQLiteRepo(db_path=":memory:")
    run = _make_run("run-1")
    repo.save_run(run)
    updated = _make_run("run-1")
    updated.total_tasks = 99
    repo.save_run(updated)

    with repo._session_factory() as session:
        from core.adapters.sqlite_repo import RunORM

        rows = session.query(RunORM).filter(RunORM.run_id == "run-1").all()
        assert len(rows) == 1
        assert rows[0].total_tasks == 99


def test_list_runs_returns_saved_run_metadata_most_recent_first():
    """list_runs() reflects every save_run() call, ordered by started_at descending, reconstructed as real RunRecord entities."""
    repo = SQLiteRepo(db_path=":memory:")
    run_a = _make_run("run-a")
    run_a.started_at = "2026-08-21T00:00:00Z"
    run_b = _make_run("run-b")
    run_b.started_at = "2026-08-21T01:00:00Z"
    repo.save_run(run_a)
    repo.save_run(run_b)

    runs = repo.list_runs()
    assert [r.run_id for r in runs] == ["run-b", "run-a"]
    assert runs[0].total_tasks == 2
    assert runs[0].config.student_models == ["qwen:latest"]


def test_list_runs_on_empty_repo_returns_empty_list():
    """list_runs() on a fresh repository with no runs returns [] rather than erroring."""
    repo = SQLiteRepo(db_path=":memory:")
    assert repo.list_runs() == []


def test_save_run_stamps_last_synced_at_and_get_sync_status_reports_it():
    """save_run() records its own write time (not the run's started_at) -- get_sync_status()
    exposes it for the /db_export page's "Export status" column."""
    repo = SQLiteRepo(db_path=":memory:")
    repo.save_run(_make_run("run-1"))

    status = repo.get_sync_status()

    assert set(status.keys()) == {"run-1"}
    # A real ISO 8601 timestamp, not the fixture's started_at ("2026-08-21T00:00:00Z") -- proves
    # this is save_run's own clock, not a copy of the RunRecord field.
    from datetime import datetime

    parsed = datetime.fromisoformat(status["run-1"])
    assert parsed.year >= 2026


def test_get_sync_status_omits_runs_never_saved():
    """A run_id that was never save_run()'d is simply absent from the dict, not None or a KeyError."""
    repo = SQLiteRepo(db_path=":memory:")
    repo.save_run(_make_run("run-a"))

    status = repo.get_sync_status()

    assert "run-b" not in status


def test_save_run_twice_updates_last_synced_at_to_the_newer_write():
    """Re-exporting an already-synced run refreshes its timestamp, matching the merge/upsert
    behavior save_run already has for the rest of the row."""
    import time

    repo = SQLiteRepo(db_path=":memory:")
    repo.save_run(_make_run("run-1"))
    first = repo.get_sync_status()["run-1"]
    time.sleep(0.01)
    repo.save_run(_make_run("run-1"))
    second = repo.get_sync_status()["run-1"]

    assert second > first


def test_opening_a_database_created_before_last_synced_at_existed_self_heals(tmp_path):
    """A pre-2026-08-25 database's runs table lacks last_synced_at entirely -- confirmed by
    building one by hand (bypassing SQLiteRepo's current schema) rather than assumed. Opening it
    through SQLiteRepo must not raise OperationalError; it should transparently add the column."""
    import sqlalchemy

    db_path = str(tmp_path / "old_schema.db")
    old_engine = sqlalchemy.create_engine(f"sqlite:///{db_path}")
    with old_engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE runs (run_id VARCHAR PRIMARY KEY, started_at VARCHAR, "
            "total_tasks INTEGER, config_json JSON)"
        )
        conn.exec_driver_sql(
            "INSERT INTO runs (run_id, started_at, total_tasks, config_json) "
            "VALUES ('run-old', '2026-08-20T00:00:00Z', 1, '{}')"
        )
        conn.commit()
    old_engine.dispose()

    repo = SQLiteRepo(db_path=db_path)  # must not raise

    with repo._session_factory() as session:
        from core.adapters.sqlite_repo import RunORM

        row = session.get(RunORM, "run-old")
        assert row.last_synced_at == ""  # migrated column default, never overwritten by save_run
    # And the repo is now fully usable, including writing a fresh sync timestamp.
    repo.save_run(_make_run("run-new"))
    assert repo.get_sync_status()["run-new"] != ""
