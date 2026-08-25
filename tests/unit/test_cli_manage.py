"""
Tests for :mod:`cli.manage` -- the operational console (``serve``/``status``/``list-runs``/
``export-db``). Each subcommand's real dependency (``uvicorn.run``, the status checks,
``JSONLStore``, ``export_run_to_db``) is monkeypatched at the point ``cli.manage`` imports it, not
mocked out at a lower level -- so these tests exercise the real argument parsing and dispatch, only
faking the side-effecting call each command ultimately makes.
"""

import pytest

from cli.manage import build_parser, main
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from core.services.db_export import DBExportError


def _make_run(run_id, started_at="2026-08-21T00:00:00Z", total_tasks=2):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["formal"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


# --- serve -------------------------------------------------------------------


def test_serve_calls_uvicorn_run_with_the_parsed_host_and_port(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.append((app, kwargs)))

    exit_code = main(["serve", "--host", "0.0.0.0", "--port", "9000"])

    assert exit_code == 0
    assert calls == [("api.app:app", {"host": "0.0.0.0", "port": 9000, "reload": True})]


def test_serve_no_reload_flag_disables_reload(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.append(kwargs))

    main(["serve", "--no-reload"])

    assert calls[0]["reload"] is False


# --- status ------------------------------------------------------------------


def test_status_prints_every_check_and_returns_0_when_all_ok(monkeypatch, capsys):
    monkeypatch.setattr("cli.manage.check_ollama", lambda: {"name": "Ollama", "ok": True, "detail": "2 model(s)"})
    monkeypatch.setattr("cli.manage.check_nltk", lambda: {"name": "NLTK", "ok": True, "detail": "5 resource(s)"})
    monkeypatch.setattr("cli.manage.check_spacy", lambda: {"name": "spaCy", "ok": True, "detail": "installed"})

    exit_code = main(["status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[OK  ] Ollama: 2 model(s)" in captured.out
    assert "[OK  ] NLTK: 5 resource(s)" in captured.out
    assert "[OK  ] spaCy: installed" in captured.out


def test_status_returns_1_when_any_check_fails(monkeypatch, capsys):
    monkeypatch.setattr("cli.manage.check_ollama", lambda: {"name": "Ollama", "ok": False, "detail": "unreachable"})
    monkeypatch.setattr("cli.manage.check_nltk", lambda: {"name": "NLTK", "ok": True, "detail": "5 resource(s)"})
    monkeypatch.setattr("cli.manage.check_spacy", lambda: {"name": "spaCy", "ok": True, "detail": "installed"})

    exit_code = main(["status"])

    assert exit_code == 1
    assert "[FAIL] Ollama: unreachable" in capsys.readouterr().out


# --- list-runs ---------------------------------------------------------------


def test_list_runs_prints_every_run_most_recent_first(monkeypatch, capsys):
    runs = [_make_run("run-b", "2026-08-21T01:00:00Z"), _make_run("run-a", "2026-08-21T00:00:00Z")]
    monkeypatch.setattr("cli.manage.JSONLStore", lambda: type("R", (), {"list_runs": staticmethod(lambda: runs)})())

    exit_code = main(["list-runs"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "run-b" in captured.out
    assert "run-a" in captured.out
    assert captured.out.index("run-b") < captured.out.index("run-a")


def test_list_runs_with_no_runs_prints_a_clear_message_not_a_blank_screen(monkeypatch, capsys):
    monkeypatch.setattr("cli.manage.JSONLStore", lambda: type("R", (), {"list_runs": staticmethod(lambda: [])})())

    exit_code = main(["list-runs"])

    assert exit_code == 0
    assert "No runs found." in capsys.readouterr().out


# --- export-db -----------------------------------------------------------------


def test_export_db_prints_a_success_message_and_returns_0(monkeypatch, capsys):
    monkeypatch.setattr("cli.manage.JSONLStore", lambda: object())
    monkeypatch.setattr(
        "cli.manage.export_run_to_db",
        lambda source, run_id, db_path, overwrite: {
            "run_id": run_id,
            "db_path": db_path,
            "response_count": 42,
            "overwritten": False,
        },
    )

    exit_code = main(["export-db", "run-1"])

    assert exit_code == 0
    assert "Exported 42 response(s) to results/nn_lab.db" in capsys.readouterr().out


def test_export_db_passes_through_custom_db_path_and_overwrite_flag(monkeypatch):
    monkeypatch.setattr("cli.manage.JSONLStore", lambda: object())
    captured_kwargs = {}

    def _fake_export(source, run_id, db_path, overwrite):
        captured_kwargs["db_path"] = db_path
        captured_kwargs["overwrite"] = overwrite
        return {"run_id": run_id, "db_path": db_path, "response_count": 1, "overwritten": overwrite}

    monkeypatch.setattr("cli.manage.export_run_to_db", _fake_export)

    main(["export-db", "run-1", "--db-path", "custom.db", "--overwrite"])

    assert captured_kwargs == {"db_path": "custom.db", "overwrite": True}


def test_export_db_on_error_prints_to_stderr_and_returns_1(monkeypatch, capsys):
    monkeypatch.setattr("cli.manage.JSONLStore", lambda: object())

    def _raise(source, run_id, db_path, overwrite):
        raise DBExportError(f"No responses found for run '{run_id}' in the source repository.")

    monkeypatch.setattr("cli.manage.export_run_to_db", _raise)

    exit_code = main(["export-db", "never-started"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: No responses found" in captured.err


# --- argument parsing / dispatch ------------------------------------------------


def test_build_parser_requires_a_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_build_parser_export_db_requires_a_run_id():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["export-db"])
