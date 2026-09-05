"""
Tests for :mod:`cli.run_experiment` -- Stage 15's config-driven batch
runner. ``run()`` is exercised against a real ``ExperimentRunner`` wired
with the same fake adapters (:class:`~tests.unit.test_experiment_runner
.FakeLLMClient`/``FakeRepository``/``FakePromptStrategy``/``FakeJudge``)
Stage 6's own tests use -- no orchestration logic is duplicated or mocked
out, only the adapters are fake. ``main()`` is exercised end to end
against a real temp TOML file, with :func:`cli.run_experiment.build_runner`
monkeypatched to return the same fake-wired runner (avoiding a real Ollama
call for a test).
"""

import io
import textwrap

import pytest

from cli.run_experiment import load_config, main, run
from core.domain.entities import ExperimentConfig, PromptMode
from core.services.experiment_runner import ExperimentRunner
from tests.unit.test_experiment_runner import FakeJudge, FakeLLMClient, FakePromptStrategy, FakeRepository

_VALID_TOML = """
    student_models = ["qwen:latest"]
    teacher_model = "llama3:latest"
    archetypes = ["Detached", "Expressive"]
    biases = ["formal"]
    prompt_mode = "Behavioral conditioning (Tuned)"
    base_temperature = 0.7
"""


def _write_toml(tmp_path, content: str):
    path = tmp_path / "experiment.toml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _fake_runner() -> ExperimentRunner:
    return ExperimentRunner(
        llm_client=FakeLLMClient(),
        repository=FakeRepository(),
        prompt_strategy=FakePromptStrategy(),
        judge=FakeJudge(verdict=True),
        archetypes={"Detached": {"about": "detached archetype"}, "Expressive": {"about": "expressive archetype"}},
    )


# --- load_config -------------------------------------------------------


def test_load_config_parses_a_valid_toml_file_into_experiment_config(tmp_path):
    """A well-formed TOML file loads into an ExperimentConfig with the exact declared values."""
    path = _write_toml(tmp_path, _VALID_TOML)

    config = load_config(path)

    assert config.student_models == ["qwen:latest"]
    assert config.teacher_model == "llama3:latest"
    assert config.archetypes == ["Detached", "Expressive"]
    assert config.prompt_mode == PromptMode.TUNED
    assert config.base_temperature == 0.7


def test_load_config_raises_on_a_config_missing_a_required_field(tmp_path):
    """A TOML file missing a required field (student_models) raises pydantic's own validation error, not a CLI-specific one."""
    path = _write_toml(
        tmp_path,
        """
        teacher_model = "llama3:latest"
        archetypes = ["Detached"]
        biases = ["formal"]
        prompt_mode = "Behavioral conditioning (Tuned)"
    """,
    )

    with pytest.raises(Exception):
        load_config(path)


# --- run -----------------------------------------------------------------


def test_run_prints_progress_and_done_lines_and_persists_every_response(tmp_path):
    """run() prints one progress line per response plus a final Done line, and the fake repository receives every generated response."""
    config = load_config(_write_toml(tmp_path, _VALID_TOML))
    runner = _fake_runner()
    out = io.StringIO()

    exit_code = run(runner, config, out=out)

    assert exit_code == 0
    output = out.getvalue()
    assert "[1/2] generating..." in output
    assert "[2/2] generating..." in output
    assert "Done -- 2/2 -- run " in output
    assert len(runner._repository.saved_responses) == 2


def test_run_rejects_an_invalid_config_before_starting_and_returns_1():
    """A config with a sweep_param but no resolved sweep_min/sweep_max is rejected by try_start's own validation, printed as an ERROR line, exit code 1."""
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["formal"],
        prompt_mode=PromptMode.TUNED,
        sweep_param="Temperature",
    )
    out = io.StringIO()

    exit_code = run(_fake_runner(), config, out=out)

    assert exit_code == 1
    assert "ERROR" in out.getvalue()
    assert "sweep_min/sweep_max" in out.getvalue()


def test_run_reports_an_already_running_guard_as_exit_1(tmp_path):
    """If try_start returns None (a run already in progress), run() reports it clearly rather than hanging or crashing."""
    config = load_config(_write_toml(tmp_path, _VALID_TOML))
    runner = _fake_runner()
    runner._running = True  # simulate a run already in progress
    out = io.StringIO()

    exit_code = run(runner, config, out=out)

    assert exit_code == 1
    assert "already in progress" in out.getvalue()


# --- main ------------------------------------------------------------------


def test_main_end_to_end_with_a_real_config_file_and_a_monkeypatched_runner(tmp_path, monkeypatch, capsys):
    """main() parses --config, loads the real file, and drives a (monkeypatched, fake-adapter) runner to completion."""
    path = _write_toml(tmp_path, _VALID_TOML)
    monkeypatch.setattr("cli.run_experiment.build_runner", lambda config: _fake_runner())

    exit_code = main(["--config", str(path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Done -- 2/2" in captured.out
