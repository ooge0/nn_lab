"""
Unit tests for :class:`core.services.metrics_engine.MetricsEngine` --
aggregation pinned against a fixed fixture of response records (CLAUDE.md
SS7: pin exact totals so a future change surfaces as a failing test, not a
silent drift).
"""

import pytest

from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from core.services.metrics_engine import MetricsEngine, RunNotFoundError


class FakeRepository:
    """Minimal Repository fake serving a fixed list of response records for one run_id, plus an
    optional list of RunRecord metadata for compare_judging_modes()'s self_critic/teacher_model
    labeling."""

    def __init__(self, responses_by_run: dict, runs: "list[RunRecord] | None" = None):
        self._responses_by_run = responses_by_run
        self._runs = runs or []

    def load_responses(self, run_id=None):
        return list(self._responses_by_run.get(run_id, []))

    def list_runs(self):
        return list(self._runs)


FIXTURE_RESPONSES = [
    {
        "student": "qwen:latest",
        "teacher": "llama3:latest",
        "strategy": "Behavioral conditioning (Tuned)",
        "archetype": "Detached",
        "bias": "personalization, formal, toxic",
        "sweep_param": "Temperature",
        "val": 0.2,
        "step": "1/2",
        "duration_ms": 4000.0,
        "ms_per_word": 50.0,
        "validation_duration_ms": 1000.0,
        "rag_enabled": False,
        "rag_mode": None,
    },
    {
        "student": "phi3:latest",
        "teacher": "llama3:latest",
        "strategy": "Behavioral conditioning (Tuned)",
        "archetype": "Anxious",
        "bias": "personalization, formal, toxic",
        "sweep_param": "Temperature",
        "val": 0.8,
        "step": "2/2",
        "duration_ms": 6000.0,
        "ms_per_word": 70.0,
        "validation_duration_ms": 2000.0,
        "rag_enabled": True,
        "rag_mode": "Archetype ONLY",
    },
]


@pytest.fixture
def engine():
    return MetricsEngine(FakeRepository({"run-1": FIXTURE_RESPONSES}))


def test_summarize_run_pins_exact_totals(engine):
    """The fixed two-record fixture aggregates to exactly these totals -- any drift is a real regression."""
    summary = engine.summarize_run("run-1")

    assert summary == {
        "total_records": 2,
        "total_steps": "2/2",
        "sweep_param": "Temperature",
        "sweep_range": "0.2 - 0.8",
        "total_duration_sec": 10.0,
        "avg_ms_per_word": 60.0,
        "avg_validation_sec": 1.5,
        "teachers": ["llama3:latest"],
        "students": ["phi3:latest", "qwen:latest"],
        "prompt_strategies": ["Behavioral conditioning (Tuned)"],
        "archetypes": ["Anxious", "Detached"],
        "biases": ["personalization, formal, toxic"],
        "distinct_bias_count": 1,
        "rag_enabled": True,
        "rag_modes": ["Archetype ONLY"],
    }


def test_summarize_run_for_unknown_run_id_raises_run_not_found(engine):
    """summarize_run() on a run with no persisted responses raises RunNotFoundError rather than silently returning an empty summary."""
    with pytest.raises(RunNotFoundError):
        engine.summarize_run("never-started")


def test_summarize_run_with_no_sweep_reports_na(engine):
    """A run with no sweep_param/val on any response reports 'N/A' rather than crashing on min()/max() of nothing."""
    repo = FakeRepository(
        {
            "run-static": [
                {
                    "student": "qwen:latest",
                    "teacher": "llama3:latest",
                    "strategy": "Raw / No system prompt",
                    "archetype": "Detached",
                    "bias": "none",
                    "sweep_param": None,
                    "val": None,
                    "step": "1/1",
                    "duration_ms": 3000.0,
                    "ms_per_word": 40.0,
                    "validation_duration_ms": 500.0,
                    "rag_enabled": False,
                    "rag_mode": None,
                }
            ]
        }
    )
    summary = MetricsEngine(repo).summarize_run("run-static")

    assert summary["sweep_param"] == "N/A"
    assert summary["sweep_range"] == "N/A"
    assert summary["rag_enabled"] is False
    assert summary["rag_modes"] == []


def _config(**overrides):
    defaults = dict(
        student_models=["qwen:latest"],
        teacher_model="mistral:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    defaults.update(overrides)
    return ExperimentConfig(**defaults)


def _response(word_count, v_ok_numeric):
    """A minimal response record with just the two fields compare_judging_modes() reads."""
    return {"word_count": word_count, "v_ok_numeric": v_ok_numeric}


def test_compare_judging_modes_pins_pass_rate_and_delta_for_two_runs():
    """3/4 clean self-critic responses pass (0.75), 1/2 clean teacher-judged responses pass (0.5)
    -- delta is exactly 0.25, not recomputed loosely."""
    repo = FakeRepository(
        responses_by_run={
            "run-self-critic": [
                _response(10, 1),
                _response(12, 1),
                _response(8, 1),
                _response(15, 0),
                _response(0, 0),  # Layer-0-rejected: no real word_count, excluded from the denominator
            ],
            "run-teacher": [_response(9, 1), _response(11, 0)],
        },
        runs=[
            RunRecord(
                run_id="run-self-critic",
                started_at="2026-08-24T00:00:00",
                config=_config(self_critic=True, teacher_model=None),
                total_tasks=5,
            ),
            RunRecord(
                run_id="run-teacher",
                started_at="2026-08-24T00:05:00",
                config=_config(self_critic=False, teacher_model="mistral:latest"),
                total_tasks=2,
            ),
        ],
    )

    result = MetricsEngine(repo).compare_judging_modes("run-self-critic", "run-teacher")

    assert result["run_a"]["pass_rate"] == 0.75
    assert result["run_a"]["clean_samples"] == 4
    assert result["run_a"]["total_samples"] == 5
    assert result["run_a"]["self_critic"] is True
    assert result["run_a"]["teacher_model"] is None
    assert result["run_b"]["pass_rate"] == 0.5
    assert result["run_b"]["self_critic"] is False
    assert result["run_b"]["teacher_model"] == "mistral:latest"
    assert result["delta"] == 0.25


def test_compare_judging_modes_unknown_run_raises_run_not_found():
    repo = FakeRepository(responses_by_run={"run-a": [_response(10, 1)]})

    with pytest.raises(RunNotFoundError):
        MetricsEngine(repo).compare_judging_modes("run-a", "never-started")


def test_compare_judging_modes_run_with_only_rejected_responses_reports_none_pass_rate_not_a_crash():
    """A run where every response was Layer-0-rejected (word_count never computed) has real
    responses on disk but nothing to average -- delta must be None, not a ZeroDivisionError."""
    repo = FakeRepository(
        responses_by_run={
            "run-all-rejected": [_response(0, 0), _response(0, 0)],
            "run-normal": [_response(10, 1)],
        }
    )

    result = MetricsEngine(repo).compare_judging_modes("run-all-rejected", "run-normal")

    assert result["run_a"]["pass_rate"] is None
    assert result["run_a"]["clean_samples"] == 0
    assert result["delta"] is None


def test_compare_judging_modes_without_run_metadata_reports_unknown_labels_not_a_crash():
    """list_runs() returning nothing for a run_id (e.g. metadata not yet indexed) degrades to
    self_critic=None/teacher_model=None rather than raising."""
    repo = FakeRepository(responses_by_run={"run-a": [_response(10, 1)], "run-b": [_response(10, 0)]})

    result = MetricsEngine(repo).compare_judging_modes("run-a", "run-b")

    assert result["run_a"]["self_critic"] is None
    assert result["run_a"]["teacher_model"] is None
