"""
core.services.metrics_engine
==============================

Read-side aggregation over a completed run's persisted responses --
Stage 7 (``tab_perf``). Pure summarization of fields
:class:`~core.services.experiment_runner.ExperimentRunner` already writes
into every response record (Stage 6); no new business logic, no judge/
cascade decisions.

Ported from ``streamlit_app.py``'s ``tab_perf`` block (lines ~1081-1180),
which builds this same ``summary_data`` shape from a pandas ``DataFrame``.
One legacy display bug is *not* carried forward: the legacy "Steps" row
shows the sweep-configuration widget's ``steps`` value (how many points a
sweep was *configured* for, read straight from session state) rather than
``df['step'].iloc[-1]`` (the actual last step *reached* in the loaded data),
which it computes into ``steps_count`` and then never uses. Since this
engine only ever sees persisted data -- there is no live widget state to
read -- ``total_steps`` here is always the real, data-derived figure:
the last response's own ``step`` value (a legacy-matching ``"N/total"``
string, e.g. ``"3/12"`` -- confirmed against both ``ExperimentRunner``
and ``streamlit_app.py``'s identical ``f"{progress}/{total_tasks}"``
construction), not a count computed here.
"""

import statistics
from typing import Optional

from core.domain.entities import RunRecord
from core.domain.interfaces import Repository


class RunNotFoundError(Exception):
    """Raised by :meth:`MetricsEngine.summarize_run` when a run has no persisted responses."""


class MetricsEngine:
    """
    Aggregates one run's persisted responses into a performance summary.

    Parameters
    ----------
    repository : Repository
        Source of persisted run metadata and response records.
    """

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def summarize_run(self, run_id: str) -> dict:
        """
        Compute the ``tab_perf`` summary for one run.

        Parameters
        ----------
        run_id : str
            The run to summarize.

        Returns
        -------
        dict
            Summary fields: ``total_records``, ``total_steps``,
            ``sweep_param``, ``sweep_range``, ``total_duration_sec``,
            ``avg_ms_per_word``, ``avg_validation_sec``, ``teachers``,
            ``students``, ``prompt_strategies``, ``archetypes``, ``biases``,
            ``rag_enabled``, ``rag_modes``, ``distinct_bias_count``.

        Raises
        ------
        RunNotFoundError
            If the run has no persisted responses.
        """
        responses = self._repository.load_responses(run_id)
        if not responses:
            raise RunNotFoundError(f"No responses found for run '{run_id}'")

        vals = [r["val"] for r in responses if r.get("val") is not None]
        rag_active = any(r.get("rag_enabled") for r in responses)
        biases = sorted({r["bias"] for r in responses if "bias" in r})

        return {
            "total_records": len(responses),
            "total_steps": responses[-1].get("step", "N/A"),
            "sweep_param": responses[0].get("sweep_param") or "N/A",
            "sweep_range": f"{min(vals)} - {max(vals)}" if vals else "N/A",
            "total_duration_sec": round(sum(r.get("duration_ms", 0.0) for r in responses) / 1000, 2),
            "avg_ms_per_word": self._mean(responses, "ms_per_word"),
            "avg_validation_sec": self._mean(responses, "validation_duration_ms", divisor=1000),
            "teachers": sorted({r["teacher"] for r in responses if r.get("teacher")}),
            "students": sorted({r["student"] for r in responses if r.get("student")}),
            "prompt_strategies": sorted({r["strategy"] for r in responses if r.get("strategy")}),
            "archetypes": sorted({r["archetype"] for r in responses if r.get("archetype")}),
            "biases": biases,
            "distinct_bias_count": len(biases),
            "rag_enabled": rag_active,
            "rag_modes": sorted({r["rag_mode"] for r in responses if r.get("rag_mode")}) if rag_active else [],
        }

    def compare_judging_modes(self, run_id_a: str, run_id_b: str) -> dict:
        """
        Compare pass rate between two runs -- built for the self-critic-vs-teacher-judging use
        case (CLAUDE.md SS4's "self-critic vs cross-model pass-rate delta" item), but generic over
        any two run IDs.

        This is a *diagnostic* comparison, not a correctness check: neither run's pass rate is
        ground truth, since both a self-critic judge and a teacher judge carry their own biases
        (LLM-as-judge self-preference is a documented phenomenon -- Zheng et al. 2023). The value
        here is the *delta* between two judging modes over the same kind of generated content, not
        either number in isolation. A large delta indicates a model inflates its own self-critic
        score relative to an outside judge; a small delta means the cheaper self-critic run is at
        least broadly consistent with the teacher-judged one for that model. Only a periodic human
        spot-check (out of scope here) can say which of the two is actually closer to correct.

        Parameters
        ----------
        run_id_a, run_id_b : str
            The two runs to compare. No ordering requirement -- either may be a self-critic run,
            a teacher-judged run, or (for a sanity check) the same run twice.

        Returns
        -------
        dict
            ``{"run_a": {...}, "run_b": {...}, "delta": float | None}`` -- each side has
            ``run_id``, ``pass_rate`` (mean ``v_ok_numeric`` over responses with a real
            ``word_count`` -- Layer-0-rejected responses never get metrics computed, matching
            ``web/plotting/benchmark_charts.py``'s established ``df_clean`` convention), sample
            counts, and (when the run's own metadata is available) ``self_critic``/``teacher_model``
            for labeling. ``delta`` is ``pass_rate_a - pass_rate_b``, ``None`` if either side has no
            samples with computed metrics to average over.

        Raises
        ------
        RunNotFoundError
            If either run has zero persisted responses at all (distinct from having zero *clean*
            responses, which yields a ``None`` pass rate for that side instead).
        """
        run_lookup = {run.run_id: run for run in self._repository.list_runs()}
        side_a = self._judging_mode_side(run_id_a, run_lookup.get(run_id_a))
        side_b = self._judging_mode_side(run_id_b, run_lookup.get(run_id_b))
        delta = (
            None
            if side_a["pass_rate"] is None or side_b["pass_rate"] is None
            else round(side_a["pass_rate"] - side_b["pass_rate"], 4)
        )
        return {"run_a": side_a, "run_b": side_b, "delta": delta}

    def _judging_mode_side(self, run_id: str, run_record: Optional[RunRecord]) -> dict:
        responses = self._repository.load_responses(run_id)
        if not responses:
            raise RunNotFoundError(f"No responses found for run '{run_id}'")
        clean = [r for r in responses if r.get("word_count", 0)]
        return {
            "run_id": run_id,
            "pass_rate": self._mean(clean, "v_ok_numeric"),
            "clean_samples": len(clean),
            "total_samples": len(responses),
            "self_critic": run_record.config.self_critic if run_record else None,
            "teacher_model": run_record.config.teacher_model if run_record else None,
        }

    @staticmethod
    def _mean(responses: "list[dict]", field: str, divisor: float = 1.0) -> Optional[float]:
        values = [r[field] for r in responses if field in r and r[field] is not None]
        if not values:
            return None
        return round(statistics.mean(values) / divisor, 2)


__all__ = ["MetricsEngine", "RunNotFoundError"]
