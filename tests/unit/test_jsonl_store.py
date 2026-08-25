"""
Unit tests for :class:`core.adapters.jsonl_store.JSONLStore` -- round-trip
write/read against a temp directory (no shared state with the real
``results/`` tree).
"""

from core.adapters.jsonl_store import JSONLStore
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


def test_save_run_creates_no_response_file_until_first_response(tmp_path):
    """save_run() writes a run's metadata sidecar immediately, but the response .jsonl file itself stays absent until a response is saved."""
    store = JSONLStore(results_dir=tmp_path)
    store.save_run(_make_run())
    assert list(tmp_path.glob("*.jsonl")) == []
    assert list(tmp_path.glob("*.meta.json")) != []


def test_save_response_appends_one_json_line_per_call(tmp_path):
    """Each save_response() call appends exactly one JSON line to the run's file."""
    store = JSONLStore(results_dir=tmp_path)
    run = _make_run()
    store.save_run(run)
    store.save_response(run.run_id, {"student": "qwen:latest", "v_ok": True})
    store.save_response(run.run_id, {"student": "qwen:latest", "v_ok": False})

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_load_responses_round_trips_exactly(tmp_path):
    """Responses saved via save_response() come back identical via load_responses()."""
    store = JSONLStore(results_dir=tmp_path)
    run = _make_run()
    store.save_run(run)
    store.save_response(run.run_id, {"student": "qwen:latest", "v_ok": True, "word_count": 12})
    store.save_response(run.run_id, {"student": "phi3:latest", "v_ok": False, "word_count": 7})

    loaded = store.load_responses(run.run_id)
    assert loaded == [
        {"student": "qwen:latest", "v_ok": True, "word_count": 12},
        {"student": "phi3:latest", "v_ok": False, "word_count": 7},
    ]


def test_load_responses_filters_by_run_id(tmp_path):
    """load_responses(run_id) returns only that run's responses, not other runs' in the same directory."""
    store = JSONLStore(results_dir=tmp_path)
    run_a, run_b = _make_run("run-a"), _make_run("run-b")
    store.save_run(run_a)
    store.save_run(run_b)
    store.save_response(run_a.run_id, {"student": "a"})
    store.save_response(run_b.run_id, {"student": "b"})

    assert store.load_responses(run_a.run_id) == [{"student": "a"}]
    assert store.load_responses(run_b.run_id) == [{"student": "b"}]


def test_load_responses_without_run_id_returns_all_runs(tmp_path):
    """load_responses() with no run_id returns responses across every run's file."""
    store = JSONLStore(results_dir=tmp_path)
    run_a, run_b = _make_run("run-a"), _make_run("run-b")
    store.save_run(run_a)
    store.save_run(run_b)
    store.save_response(run_a.run_id, {"student": "a"})
    store.save_response(run_b.run_id, {"student": "b"})

    all_responses = store.load_responses()
    assert len(all_responses) == 2
    assert {"student": "a"} in all_responses
    assert {"student": "b"} in all_responses


def test_load_responses_for_never_started_run_returns_empty_list(tmp_path):
    """load_responses() for a run_id with no saved responses returns [] rather than erroring."""
    store = JSONLStore(results_dir=tmp_path)
    assert store.load_responses("never-started") == []


def test_list_runs_returns_saved_run_metadata_most_recent_first(tmp_path):
    """list_runs() reflects every save_run() call, ordered by started_at descending, independent of response activity."""
    store = JSONLStore(results_dir=tmp_path)
    run_a = _make_run("run-a")
    run_a.started_at = "2026-08-21T00:00:00Z"
    run_b = _make_run("run-b")
    run_b.started_at = "2026-08-21T01:00:00Z"
    store.save_run(run_a)
    store.save_run(run_b)

    runs = store.list_runs()
    assert [r.run_id for r in runs] == ["run-b", "run-a"]
    assert runs[0].total_tasks == 2
    assert runs[0].config.student_models == ["qwen:latest"]


def test_list_runs_on_empty_store_returns_empty_list(tmp_path):
    """list_runs() on a fresh directory with no runs returns [] rather than erroring."""
    store = JSONLStore(results_dir=tmp_path)
    assert store.list_runs() == []
