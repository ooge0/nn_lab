"""
Unit tests for :mod:`core.services.db_export` -- copying one run from a source ``Repository``
(the live ``JSONLStore`` in practice, faked here) into a real :class:`~core.adapters.sqlite_repo
.SQLiteRepo`. Uses a real temp-file SQLite database (not ``:memory:``) for the target, since the
overwrite/collision behavior being tested spans two separate ``SQLiteRepo`` constructions inside
``export_run_to_db`` -- an in-memory database isn't shared across separate engine instances, so it
couldn't actually exercise "the run is already in the target DB" the way a real file can.
"""

import pytest

from core.adapters.sqlite_repo import SQLiteRepo
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from core.services.db_export import DBExportError, export_run_to_db
from tests.unit.test_experiment_runner import FakeRepository


def _make_run(run_id="run-1"):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="qwen:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at="2026-08-21T00:00:00Z", config=config, total_tasks=2)


def _source_with_one_run(run_id="run-1", n_responses=2):
    source = FakeRepository()
    source.save_run(_make_run(run_id))
    for i in range(n_responses):
        source.save_response(run_id, {"student": "qwen:latest", "v_ok_numeric": 1, "step": f"{i+1}/{n_responses}"})
    return source


def test_export_run_to_db_copies_run_metadata_and_every_response(tmp_path):
    db_path = str(tmp_path / "nn_lab.db")
    source = _source_with_one_run(n_responses=3)

    result = export_run_to_db(source, "run-1", db_path=db_path)

    assert result["run_id"] == "run-1"
    assert result["db_path"] == db_path
    assert result["response_count"] == 3
    assert result["overwritten"] is False
    assert result["synced_at"]  # a real, non-empty timestamp -- exact format pinned separately
    target = SQLiteRepo(db_path=db_path)
    assert len(target.load_responses("run-1")) == 3
    assert target.list_runs()[0].run_id == "run-1"


def test_export_run_to_db_on_completely_unknown_run_id_raises(tmp_path):
    """No run metadata and no responses at all -- a bogus/typo'd run_id."""
    db_path = str(tmp_path / "nn_lab.db")
    source = FakeRepository()

    with pytest.raises(DBExportError, match="No responses found"):
        export_run_to_db(source, "never-started", db_path=db_path)


def test_export_run_to_db_on_a_run_that_exists_but_has_no_responses_yet_raises(tmp_path):
    """A real, distinct state from 'unknown run_id': the run was started (save_run called,
    metadata exists) but hasn't produced any responses yet -- e.g. exporting the instant after
    clicking Run, or a run that was stopped before its first response landed. Same error path as
    the bogus-id case (both have zero responses to copy), but a genuinely different real condition
    -- worth pinning separately so the two don't silently drift onto different error messages later."""
    db_path = str(tmp_path / "nn_lab.db")
    source = FakeRepository()
    source.save_run(_make_run("run-just-started"))

    with pytest.raises(DBExportError, match="No responses found"):
        export_run_to_db(source, "run-just-started", db_path=db_path)


def test_export_run_to_db_second_export_without_overwrite_raises_not_duplicates(tmp_path):
    """SQLiteRepo.save_response has no dedup key -- a naive re-export would silently duplicate every
    row. Confirms the default (overwrite=False) refuses instead."""
    db_path = str(tmp_path / "nn_lab.db")
    source = _source_with_one_run(n_responses=2)
    export_run_to_db(source, "run-1", db_path=db_path)

    with pytest.raises(DBExportError, match="already has 2 response"):
        export_run_to_db(source, "run-1", db_path=db_path)

    # Confirm nothing was duplicated by the failed second attempt.
    target = SQLiteRepo(db_path=db_path)
    assert len(target.load_responses("run-1")) == 2


def test_export_run_to_db_with_overwrite_replaces_rather_than_duplicates(tmp_path):
    db_path = str(tmp_path / "nn_lab.db")
    source = _source_with_one_run(n_responses=2)
    export_run_to_db(source, "run-1", db_path=db_path)

    # Source now has a different, larger set of responses (simulating a re-run/regenerated export).
    source2 = _source_with_one_run(n_responses=5)
    result = export_run_to_db(source2, "run-1", db_path=db_path, overwrite=True)

    assert result["response_count"] == 5
    assert result["overwritten"] is True
    target = SQLiteRepo(db_path=db_path)
    assert len(target.load_responses("run-1")) == 5


def test_export_run_to_db_preserves_response_content_exactly_not_just_the_count(tmp_path):
    """Every field of every response round-trips byte-for-byte through the export -- a count-only
    assertion would pass even if the copy silently dropped or mangled fields."""
    db_path = str(tmp_path / "nn_lab.db")
    source = FakeRepository()
    source.save_run(_make_run("run-1"))
    original_responses = [
        {"student": "qwen:latest", "v_ok_numeric": 1, "archetype": "Detached", "cognitive_load": 0.42},
        {"student": "phi3:latest", "v_ok_numeric": 0, "archetype": "Anxious", "cognitive_load": 0.11},
    ]
    for response in original_responses:
        source.save_response("run-1", response)

    export_run_to_db(source, "run-1", db_path=db_path)

    target = SQLiteRepo(db_path=db_path)
    assert target.load_responses("run-1") == original_responses


def test_export_run_to_db_does_not_disturb_a_different_runs_data_already_in_the_target(tmp_path):
    """Exporting run A into a database that already holds run B's data must leave run B's rows
    untouched -- the same isolation guarantee test_delete_responses_removes_only_the_target_runs
    _rows pins at the SQLiteRepo layer, exercised here end-to-end through the real export path."""
    db_path = str(tmp_path / "nn_lab.db")
    source_b = _source_with_one_run("run-b", n_responses=3)
    export_run_to_db(source_b, "run-b", db_path=db_path)

    source_a = _source_with_one_run("run-a", n_responses=2)
    export_run_to_db(source_a, "run-a", db_path=db_path)

    target = SQLiteRepo(db_path=db_path)
    assert len(target.load_responses("run-a")) == 2
    assert len(target.load_responses("run-b")) == 3
    run_ids_in_db = {run.run_id for run in target.list_runs()}
    assert run_ids_in_db == {"run-a", "run-b"}


def test_export_run_to_db_creates_the_target_directory_if_it_does_not_exist_yet(tmp_path):
    """A fresh checkout has no results/ directory yet -- the first-ever export must not crash on a
    missing parent directory (SQLiteRepo's own __init__ already handles this; confirmed here at the
    export-service level, the actual call path a first-time user hits)."""
    db_path = str(tmp_path / "brand_new_subdir" / "nested" / "nn_lab.db")
    source = _source_with_one_run(n_responses=1)

    result = export_run_to_db(source, "run-1", db_path=db_path)

    assert result["response_count"] == 1
    assert (tmp_path / "brand_new_subdir" / "nested" / "nn_lab.db").exists()


def test_export_run_to_db_round_trips_edge_case_value_types_through_the_json_column(tmp_path):
    """None, nested lists/dicts, booleans, and unicode text must all survive the SQLite JSON column
    exactly -- a real response record has several of these (rag_chunks_count is int, teacher_model
    can be None for self-critic runs, output is free-form text)."""
    db_path = str(tmp_path / "nn_lab.db")
    source = FakeRepository()
    source.save_run(_make_run("run-1"))
    edge_case_response = {
        "student": "qwen:latest",
        "teacher": None,
        "v_ok": True,
        "v_ok_numeric": 1,
        "rag_chunks": ["chunk one", "chunk two"],
        "sweep_config": {"param": "Temperature", "steps": 3},
        "output": "Привіт — a response with unicode and an em dash",
        "duration_ms": 0.0,
    }
    source.save_response("run-1", edge_case_response)

    export_run_to_db(source, "run-1", db_path=db_path)

    target = SQLiteRepo(db_path=db_path)
    assert target.load_responses("run-1") == [edge_case_response]


def test_get_sync_status_reflects_exported_runs_and_omits_unexported_ones(tmp_path):
    """core.services.db_export.get_sync_status() is a thin wrapper around SQLiteRepo's own method
    -- confirms it's wired to the right database and doesn't invent/omit entries."""
    from core.services.db_export import get_sync_status

    db_path = str(tmp_path / "nn_lab.db")
    source = _source_with_one_run("run-exported", n_responses=1)
    export_run_to_db(source, "run-exported", db_path=db_path)

    status = get_sync_status(db_path=db_path)

    assert "run-exported" in status
    assert status["run-exported"]  # non-empty real timestamp
    assert "run-never-exported" not in status


def test_get_sync_status_on_a_database_that_does_not_exist_yet_returns_empty_not_a_crash(tmp_path):
    """A fresh checkout has no results/nn_lab.db yet -- the /db_export page's first-ever render
    must show every run as 'not synced', not 500."""
    from core.services.db_export import get_sync_status

    db_path = str(tmp_path / "brand_new" / "nn_lab.db")

    assert get_sync_status(db_path=db_path) == {}
