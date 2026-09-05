"""
core.services.experiment_runner
==================================

``ExperimentRunner`` -- orchestrates a full experiment: iterate every
(student x archetype x bias x swept-value) combination, build a prompt
(optionally RAG-augmented), generate, extract clean text, judge, compute
descriptive metrics, persist. Streams progress via the SSE +
background-thread mechanism proven in Stage 1.

Stage 5 built the narrow one-combination slice; Stage 6 (this version)
extends it to full ``tab_gen`` parity -- judge, prompt mode, parameter
sweep, RAG toggle, self-critic routing -- reusing the same runner rather
than replacing it.
"""

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from core.analysis.calculate_advanced_linguistic_metrics import calculate_advanced_linguistic_metrics
from core.analysis.hallucination_check import check_hallucination
from core.analysis.neuro_metrics import NeuroMetrics
from core.analysis.nlp_science import PsychScientist
from core.analysis.response_classification import ResponseClassification, classify_response, is_echo_response
from core.analysis.syntactic_complexity import dependency_distance
from core.domain.entities import ExperimentConfig, JudgeVerdict, RunRecord
from core.domain.interfaces import Judge, KnowledgeBase, LLMClient, PromptStrategy, Repository
from core.services._sse import bridge_to_queue

_SWEEP_PARAM_TO_KWARG = {
    "Temperature": "temperature",
    "Top P": "top_p",
    "Frequency penalty": "frequency_penalty",
    "Presence penalty": "presence_penalty",
}


def extract_best_text(raw_response: str) -> str:
    """
    Extract clean text from a model response.

    Ported unchanged from ``streamlit_app.py``'s ``extract_best_text``
    (line 180): if the response parses as a JSON object, return its
    ``"text"`` key (falling back to the raw response if that key is
    missing); otherwise, or if parsing fails for any reason, return the
    raw response as-is.

    Parameters
    ----------
    raw_response : str
        The model's raw response content.

    Returns
    -------
    str
        The extracted text.
    """
    try:
        parsed = json.loads(raw_response)
        if isinstance(parsed, dict):
            return parsed.get("text", raw_response)
        return raw_response
    except Exception:
        return raw_response


def compute_sweep_range(v_min: float, v_max: float, steps: int, ascending: bool = True) -> "list[float]":
    """
    Compute the swept value list, pinned against ``streamlit_app.py``'s
    exact formula (lines 593-603).

    Parameters
    ----------
    v_min, v_max : float
        The resolved range endpoints (already resolved from either the
        legacy "Delta" mode -- center +/- delta -- or "MIN-MAX" mode -- an
        explicit range -- by the caller; this function doesn't need to
        know which).
    steps : int
        Number of points to sample. ``steps <= 1`` returns a single-point
        list at ``v_min`` (matching the legacy ``else: val_range =
        [v_min]`` fallback), not an error.
    ascending : bool, optional
        Sort direction (default ``True``). The legacy app only ever
        applies explicit sorting for "Delta" mode (MIN-MAX's UI disables
        the ASC/DESC checkboxes entirely, since the range is already
        ordered by construction) -- callers resolving a MIN-MAX range
        should always pass ``ascending=True`` to match.

    Returns
    -------
    list[float]
        Values linearly interpolated between ``v_min`` and ``v_max``,
        rounded to 2 decimals, in the requested order.
    """
    if steps <= 1:
        return [round(v_min, 2)]
    values = [round(v_min + (v_max - v_min) * i / (steps - 1), 2) for i in range(steps)]
    return sorted(values, reverse=not ascending)


@dataclass
class RunProgressEvent:
    """
    A single progress update pushed from the background thread to the SSE
    stream.

    Parameters
    ----------
    stage : str
        Human-readable stage name (``"started"``, ``"generating"``,
        ``"done"``, ``"error"``).
    done : bool, optional
        ``True`` on the terminal event that closes the stream.
    run_id : str, optional
        The run's ID, included once known.
    step, total_tasks : int, optional
        Progress counters, once the run's full task count is known.
    error : str, optional
        Error message, set only when ``stage == "error"``.
    """

    stage: str
    done: bool = False
    run_id: Optional[str] = None
    step: Optional[int] = None
    total_tasks: Optional[int] = None
    error: Optional[str] = None


class InvalidExperimentConfigError(ValueError):
    """
    Raised by :meth:`ExperimentRunner.try_start` when a config is missing
    a field required by the settings it declares -- caught before any
    generation starts, not discovered mid-run.
    """


class _StopRequested(Exception):
    """Internal control-flow signal only -- breaks `_run`'s nested loop cleanly once `request_stop()` is called; never raised across the `_run`/`_run_one` boundary into caller code."""


class TooManyTasksError(Exception):
    """
    Raised by :meth:`ExperimentRunner.try_start` when a run's computed
    ``total_tasks`` exceeds the configured cap
    (``config.ini``'s ``[EXPERIMENT] max_total_tasks``) -- refused before
    any generation starts, not truncated mid-run.

    Parameters
    ----------
    total_tasks : int
        The computed task count that triggered the refusal.
    max_total_tasks : int
        The configured cap it exceeded.
    """

    def __init__(self, total_tasks: int, max_total_tasks: int) -> None:
        self.total_tasks = total_tasks
        self.max_total_tasks = max_total_tasks
        super().__init__(
            f"Run would take {total_tasks} generation calls, exceeding the configured cap of "
            f"{max_total_tasks} ([EXPERIMENT] max_total_tasks in config.ini)."
        )


class ExperimentRunner:
    """
    Runs a full experiment (every student x archetype x bias x
    swept-value combination) on a background thread, judging and
    persisting each response, and streams progress.

    Parameters
    ----------
    llm_client : LLMClient
        Client used to generate responses.
    repository : Repository
        Storage for the run's metadata and its responses.
    prompt_strategy : PromptStrategy
        Builds each system prompt from archetype/bias/mode.
    judge : Judge
        Evaluates each response that survives the Layer 0/Layer 1 gates
        (:mod:`core.analysis.response_classification`, checked before this
        is ever called -- see :meth:`_run_one`). :class:`~core.adapters.structured_judge.StructuredJudge`
        today, by explicit author decision (CLAUDE.md SS4/SS6) -- Layer 2
        (NLI/specialized classifiers) is not built; this class needs no
        change if that lands later, since ``Judge`` is the seam.
    archetypes : dict
        The archetypes definition (same dict `NaivePromptStrategy` is
        constructed with) -- used here only to look up each archetype's
        ``"about"`` text for the persisted record, a metadata concern kept
        separate from `PromptStrategy`'s job of building prompt text.
    knowledge_base : KnowledgeBase, optional
        RAG retrieval, used only when a run's config sets ``rag_enabled``.
        Omit if RAG is never going to be used -- a run that tries to
        enable RAG without one configured fails clearly at run time.
    max_total_tasks : int, optional
        Hard cap on a single run's total generation-call count (see
        `TooManyTasksError`). ``None`` disables the cap -- callers should
        pass ``utils.config_loader_short.MAX_TOTAL_TASKS`` in production.

    Notes
    -----
    Enforces the same single-run concurrent guard as Stage 1's
    ``DemoRunner`` -- single-user, single-session per the project's
    deployment constraints.

    Metrics (`PsychScientist`/`NeuroMetrics`/
    `calculate_advanced_linguistic_metrics`) are computed here, inline,
    per response -- matching the legacy `entry` dict's own behaviour
    (``streamlit_app.py`` merges them into the same record before saving,
    not as a deferred pass), and only *after* extraction and Layer 0
    classification (:mod:`core.analysis.response_classification`,
    CLAUDE.md SS1), which now genuinely gates this seam: a Layer-0-rejected
    response (``EMPTY``/``MALFORMED_JSON``/``TRUNCATED``/``SCHEMA_ERROR``)
    skips metrics computation and the judge call entirely, by explicit
    author decision (CLAUDE.md SS4/SS6) -- see :meth:`_run_one`. Layer 1
    (a narrow, real-data-calibrated echo detector, not the full topical-STS
    gate CLAUDE.md SS3a describes) runs after metrics, since it reuses the
    ``semantic_overlap`` value metrics computation already produces. Layer 2
    (NLI/specialized classifiers) remains unbuilt.

    A real bug found while wiring this, fixed rather than ported forward:
    ``nlp_stats``/``neuro_stats`` both compute ``self_focus`` (different
    pronoun sets), and ``nlp_stats``/``base_metrics`` both compute
    ``word_count``/``ms_per_word`` (different tokenization). The legacy
    app's plain dict-update merge silently lets whichever computation runs
    last win, discarding the other -- observed losing ``nlp_stats``' more
    accurate ``self_focus`` in favour of a wrong ``0.0``. Resolved at the
    merge point (see :meth:`_run_one`) by renaming the losing side's key,
    matching the ``_ext`` suffix convention ``neuro_metrics.py`` already
    uses for its other overlapping fields.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        repository: Repository,
        prompt_strategy: PromptStrategy,
        judge: Judge,
        archetypes: dict,
        knowledge_base: Optional[KnowledgeBase] = None,
        max_total_tasks: Optional[int] = None,
    ) -> None:
        self._llm_client = llm_client
        self._repository = repository
        self._prompt_strategy = prompt_strategy
        self._judge = judge
        self._archetypes = archetypes
        self._knowledge_base = knowledge_base
        self._max_total_tasks = max_total_tasks
        self._lock = threading.Lock()
        self._running = False
        self._queue: Optional["asyncio.Queue[RunProgressEvent]"] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()

    @property
    def running(self) -> bool:
        """bool: Whether a run is currently in progress."""
        with self._lock:
            return self._running

    def request_stop(self) -> bool:
        """
        Ask the in-progress run to halt after its current response finishes.

        Cooperative, not preemptive: the background thread only checks this
        between tasks (see `_run`'s loop), so a call to `LLMClient.generate`
        already in flight always completes and gets persisted before the
        run actually stops -- there is no way to safely abort an
        in-progress generation call without deeper changes to the
        `LLMClient` adapters themselves, which this method deliberately
        does not attempt. Restores the legacy sidebar's "Stop generation"
        button (``streamlit_app.py``'s ``trigger_stop``/``stop_requested``),
        dropped during the rewrite and never rebuilt until now.

        Returns
        -------
        bool
            ``True`` if a run was actually in progress and has been asked
            to stop; ``False`` if nothing was running (nothing to stop).
        """
        with self._lock:
            if not self._running:
                return False
            self._stop_requested.set()
            return True

    @property
    def queue(self) -> Optional["asyncio.Queue[RunProgressEvent]"]:
        """Optional[asyncio.Queue[RunProgressEvent]]: The active run's queue, or ``None`` if none has started."""
        return self._queue

    @property
    def max_total_tasks(self) -> Optional[int]:
        """Optional[int]: The configured cap, or ``None`` if uncapped."""
        return self._max_total_tasks

    def set_knowledge_base(self, knowledge_base: KnowledgeBase) -> None:
        """
        Attach (or replace) the ``KnowledgeBase`` used for RAG-enabled runs.

        Parameters
        ----------
        knowledge_base : KnowledgeBase

        Notes
        -----
        Exists so callers can build the (expensive -- loads a
        SentenceTransformer model) knowledge base lazily, on first actual
        RAG-enabled request, rather than paying that cost unconditionally
        at construction time for a feature that's optional per-run.
        """
        self._knowledge_base = knowledge_base

    @staticmethod
    def compute_total_tasks(config: ExperimentConfig) -> int:
        """
        Compute a config's total generation-call count, without starting
        anything -- callers (e.g. an API handler) can use this to show a
        preview before the user commits, matching the legacy app's
        ``total_tasks_preview`` display.

        Parameters
        ----------
        config : ExperimentConfig

        Returns
        -------
        int
        """
        val_range_len = 1 if not config.sweep_param else max(1, config.sweep_steps)
        return len(config.student_models) * len(config.archetypes) * len(config.biases) * val_range_len

    def try_start(
        self, loop: asyncio.AbstractEventLoop, config: ExperimentConfig
    ) -> Optional["asyncio.Queue[RunProgressEvent]"]:
        """
        Attempt to start a new run (the concurrent-run guard and the
        `TooManyTasksError` cap check).

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop of the request starting the run.
        config : ExperimentConfig
            The full experiment configuration.

        Returns
        -------
        Optional[asyncio.Queue[RunProgressEvent]]
            A fresh queue for the new run, or ``None`` if a run was
            already in progress.

        Raises
        ------
        InvalidExperimentConfigError
            If ``config`` declares a sweep without a resolved
            ``sweep_min``/``sweep_max`` range, or omits ``teacher_model``
            while ``self_critic`` is ``False`` (matches the legacy app's
            own "Teacher" field validation -- ``missing_params`` in
            ``streamlit_app.py``).
        TooManyTasksError
            If ``config``'s computed task count exceeds
            ``max_total_tasks`` -- raised before the concurrent-run guard
            is even checked, so it never falsely reports "already
            running" for an oversized request.
        """
        if config.sweep_param and (config.sweep_min is None or config.sweep_max is None):
            raise InvalidExperimentConfigError(
                f"sweep_param={config.sweep_param!r} is set but sweep_min/sweep_max were not resolved."
            )
        if not config.self_critic and not config.teacher_model:
            raise InvalidExperimentConfigError("teacher_model is required when self_critic is False.")

        total_tasks = self.compute_total_tasks(config)
        if self._max_total_tasks is not None and total_tasks > self._max_total_tasks:
            raise TooManyTasksError(total_tasks, self._max_total_tasks)

        with self._lock:
            if self._running:
                return None
            self._running = True
            self._stop_requested.clear()
            self._queue = asyncio.Queue()
            queue = self._queue

        self._thread = threading.Thread(target=self._run, args=(loop, queue, config, total_tasks), daemon=True)
        self._thread.start()
        return queue

    def _run(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: "asyncio.Queue[RunProgressEvent]",
        config: ExperimentConfig,
        total_tasks: int,
    ) -> None:
        """Background-thread body: iterate the full grid, judge and persist each response."""
        try:
            if not self._try_bridge(loop, queue, RunProgressEvent(stage="started", total_tasks=total_tasks)):
                return

            run = RunRecord(
                run_id=f"run-{int(time.time() * 1000)}",
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                config=config,
                total_tasks=total_tasks,
            )
            self._repository.save_run(run)

            val_range: "list[Optional[float]]"
            if config.sweep_param:
                assert config.sweep_min is not None and config.sweep_max is not None  # guaranteed by try_start
                val_range = list(
                    compute_sweep_range(config.sweep_min, config.sweep_max, config.sweep_steps, config.sweep_ascending)
                )
            else:
                val_range = [None]

            step = 0
            try:
                for student in config.student_models:
                    for archetype in config.archetypes:
                        for bias in config.biases:
                            for v_val in val_range:
                                if self._stop_requested.is_set():
                                    raise _StopRequested()
                                step += 1
                                self._run_one(
                                    loop, queue, run, config, student, archetype, bias, v_val, step, total_tasks
                                )
            except _StopRequested:
                self._try_bridge(
                    loop,
                    queue,
                    RunProgressEvent(stage="stopped", run_id=run.run_id, step=step, total_tasks=total_tasks, done=True),
                )
                return

            self._try_bridge(
                loop,
                queue,
                RunProgressEvent(stage="done", run_id=run.run_id, step=step, total_tasks=total_tasks, done=True),
            )
        except Exception as exc:
            logger.exception(f"ExperimentRunner: run failed: {exc}")
            self._try_bridge(loop, queue, RunProgressEvent(stage="error", error=str(exc), done=True))
        finally:
            with self._lock:
                self._running = False

    def _run_one(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: "asyncio.Queue[RunProgressEvent]",
        run: RunRecord,
        config: ExperimentConfig,
        student: str,
        archetype: str,
        bias: str,
        v_val: Optional[float],
        step: int,
        total_tasks: int,
    ) -> None:
        """Generate, judge, measure, and persist one response."""
        params = {
            "temperature": config.base_temperature,
            "top_p": config.base_top_p,
            "frequency_penalty": config.base_frequency_penalty,
            "presence_penalty": config.base_presence_penalty,
        }
        if v_val is not None and config.sweep_param:
            params[_SWEEP_PARAM_TO_KWARG[config.sweep_param]] = v_val

        rag_query, rag_chunks, rag_context = "", [], ""
        if config.rag_enabled and self._knowledge_base is not None:
            if config.rag_mode == "Archetype ONLY":
                rag_query = archetype
            elif config.rag_mode == "Archetype + Bias":
                rag_query = f"{archetype} {bias}"
            else:
                rag_query = bias
            rag_chunks = self._knowledge_base.retrieve(rag_query, top_k=config.rag_top_k or 5)
            rag_context = "\n\n".join(f"[{c['archetype']} | {c['category']}]\n{c['text']}" for c in rag_chunks)

        system_prompt = self._prompt_strategy.build(
            archetype, bias, config.prompt_mode, exclude_archetype_from_prompt=config.exclude_archetype_from_prompt
        )
        if rag_context:
            user_prompt = (
                f"TASK:\n{bias}\n\nREFERENCE KNOWLEDGE:\n{rag_context}\n\nINSTRUCTION:\n"
                f"Generate response using retrieved archetype information with bias: {bias}."
            )
        else:
            user_prompt = bias

        result = self._llm_client.generate(
            student,
            system_prompt,
            user_prompt,
            max_tokens=config.max_tokens,
            seed=config.seed,
            json_mode=True,
            **params,
        )
        clean_text = extract_best_text(result.text)

        if config.self_critic:
            judge_model = student
        else:
            assert config.teacher_model is not None  # guaranteed by try_start
            judge_model = config.teacher_model

        base_fields = self._base_entry_fields(
            config,
            student,
            archetype,
            bias,
            v_val,
            step,
            total_tasks,
            system_prompt,
            judge_model,
            clean_text,
            result,
            rag_query,
            rag_chunks,
            rag_context,
        )

        # Layer 0 (CLAUDE.md SS1): deterministic classification of the RAW response, before
        # metrics computation or a judge call ever touch it. A garbage response (empty/malformed/
        # truncated/wrong-schema) skips both entirely -- the real, measured-as-costly compute this
        # module's class docstring names, and a full LLM judge round-trip on top of it.
        layer0_classification = classify_response(result.text)
        if layer0_classification != ResponseClassification.VALID:
            entry = {
                **base_fields,
                "layer0_classification": layer0_classification.value,
                "layer1_echo_detected": False,
                "v_ok": False,
                "v_ok_numeric": 0,
                "v_confidence": 1.0,
                "v_rationale": f"Rejected by Layer 0 (cascade): {layer0_classification.value}.",
                "validation_duration_ms": 0.0,
            }
            self._repository.save_response(run.run_id, entry)
            self._try_bridge(
                loop, queue, RunProgressEvent(stage="generating", run_id=run.run_id, step=step, total_tasks=total_tasks)
            )
            return

        sci = PsychScientist()
        neuro = NeuroMetrics(sci.sia)
        nlp_stats = sci.analyze_text(clean_text, result.duration_ms)
        neuro_stats = neuro.compute(clean_text)
        base_metrics_dict = calculate_advanced_linguistic_metrics(bias, clean_text, result.duration_ms).model_dump()
        # Syntactic complexity (2026-08-24, CLAUDE.md SS7's textdescriptives/spaCy adoption) -- a
        # fourth, independent metric source, kept separate from the three above rather than folded
        # into one of them, since it's the only spaCy-based (not NLTK-based) computation in the
        # pipeline. New field name, no merge-collision risk with the dict.update() calls below.
        base_metrics_dict["dependency_distance"] = dependency_distance(clean_text)

        # Real, silent data-loss bug found while wiring this: nlp_stats and
        # neuro_stats both compute "self_focus" (different pronoun sets --
        # nlp_stats' is broader, including we/us/our), and nlp_stats and
        # base_metrics_dict both compute "word_count"/"ms_per_word"
        # (different tokenization -- NLTK vs naive .split()). The legacy
        # app's plain `entry.update(nlp_stats); entry.update(neuro_stats);
        # entry.update(base_metrics)` silently lets the later dict overwrite
        # the earlier one on collision -- observed losing nlp_stats' more
        # accurate self_focus value in favour of a wrong 0.0 from neuro_stats
        # on real text. neuro_metrics.py already suffixes six of its seven
        # overlapping fields with "_ext" for exactly this reason
        # (abstract_ratio_ext, modality_ext, sentiment_variance_ext) --
        # self_focus was the one case that convention wasn't applied to.
        # Fixed here, at the merge point, rather than silently porting the
        # collision (and rather than touching the pre-existing, tested
        # metric-computation modules themselves).
        neuro_stats["self_focus_ext"] = neuro_stats.pop("self_focus")
        base_metrics_dict["word_count_raw"] = base_metrics_dict.pop("word_count")
        base_metrics_dict["ms_per_word_raw"] = base_metrics_dict.pop("ms_per_word")

        # Layer 1: a narrow, real-data-calibrated echo detector (CLAUDE.md SS3a names a broader
        # topical-STS gate this doesn't fully implement -- see response_classification.py's own
        # docstring). Reuses semantic_overlap, just computed above -- no second embedding call.
        echo_detected = is_echo_response(base_metrics_dict["semantic_overlap"])

        # Layer 2 (2026-08-24): NLI factual-contradiction check against RAG-retrieved context --
        # only meaningful, and only run, when RAG is enabled (rag_context non-empty). Deliberately
        # non-gating: logs a real contradiction score/predicted label but does not affect v_ok,
        # since no real-data calibration exists yet for a rejection threshold (see
        # hallucination_check.py's own docstring for why that matters).
        layer2_result = check_hallucination(clean_text, rag_context)

        v_start = time.time()
        if echo_detected:
            verdict = JudgeVerdict(
                verdict=False,
                confidence=1.0,
                rationale="Rejected by Layer 1 (cascade): response echoes its own bias/archetype "
                "instruction instead of generating conditioned text.",
            )
        else:
            verdict = self._judge.evaluate(clean_text, archetype, bias, judge_model)
        v_dur = (time.time() - v_start) * 1000

        entry = {
            **base_fields,
            "layer0_classification": layer0_classification.value,
            "layer1_echo_detected": echo_detected,
            "layer2_checked": layer2_result["checked"],
            "layer2_predicted_label": layer2_result["predicted_label"],
            "layer2_contradiction_score": layer2_result["contradiction_score"],
            "v_ok": verdict.verdict,
            "v_ok_numeric": int(verdict.verdict),
            "v_confidence": verdict.confidence,
            "v_rationale": verdict.rationale,
            "validation_duration_ms": v_dur,
        }
        entry.update(nlp_stats)
        entry.update(neuro_stats)
        entry.update(base_metrics_dict)

        self._repository.save_response(run.run_id, entry)
        self._try_bridge(
            loop,
            queue,
            RunProgressEvent(stage="generating", run_id=run.run_id, step=step, total_tasks=total_tasks),
        )

    def _base_entry_fields(
        self,
        config: ExperimentConfig,
        student: str,
        archetype: str,
        bias: str,
        v_val: Optional[float],
        step: int,
        total_tasks: int,
        system_prompt: str,
        judge_model: str,
        clean_text: str,
        result,
        rag_query: str,
        rag_chunks: list,
        rag_context: str,
    ) -> dict:
        """
        Fields every persisted entry gets regardless of Layer 0/1 outcome -- generation, RAG, and
        run metadata, none of which depend on metrics computation or a judge call. Shared between
        the Layer-0-rejected short-circuit path and the full-metrics path in ``_run_one`` so the
        two can't silently drift out of sync with each other.
        """
        return {
            "batch": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tasks": total_tasks,
            "steps": step,
            "step": f"{step}/{total_tasks}",
            "strategy": config.prompt_mode.value,
            "archetype": archetype,
            "bias": bias,
            "system_prompt": system_prompt,
            "archetype_about": self._archetypes.get(archetype, {}).get("about"),
            "student": student,
            "teacher": judge_model,
            "sweep_param": config.sweep_param or "Baseline",
            "val": v_val if v_val is not None else config.base_temperature,
            "output": clean_text,
            "duration_ms": result.duration_ms,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "ollama_total_duration_ms": result.ollama_total_duration_ms,
            "ollama_load_duration_ms": result.ollama_load_duration_ms,
            "ollama_prompt_eval_duration_ms": result.ollama_prompt_eval_duration_ms,
            "ollama_eval_duration_ms": result.ollama_eval_duration_ms,
            "tokens_per_second": (
                round(result.completion_tokens / (result.ollama_eval_duration_ms / 1000), 2)
                if result.completion_tokens and result.ollama_eval_duration_ms
                else None
            ),
            "rag_enabled": config.rag_enabled,
            "rag_mode": config.rag_mode if config.rag_enabled else None,
            "rag_top_k": config.rag_top_k if config.rag_enabled else None,
            "rag_query": rag_query,
            "rag_chunks_count": len(rag_chunks),
            "rag_context_chars": len(rag_context),
            "rag_context": rag_context,
            "val_temperature": config.base_temperature,
            "val_top_p": config.base_top_p,
            "val_frequency_penalty": config.base_frequency_penalty,
            "val_presence_penalty": config.base_presence_penalty,
        }

    @staticmethod
    def _try_bridge(
        loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[RunProgressEvent]", event: RunProgressEvent
    ) -> bool:
        """
        Bridge one event, tolerating a closed event loop (the real Ctrl+C
        mid-run case).

        Returns
        -------
        bool
            ``True`` if the event was scheduled, ``False`` if the loop was
            already closed (nobody can receive it either way).

        Notes
        -----
        Deliberately narrower than catching ``RuntimeError`` around the
        whole run: ``LLMClient.generate`` and ``Repository`` calls can also
        raise ``RuntimeError`` for unrelated reasons (e.g. a real
        connection failure), and those must still surface as an ``error``
        progress event, not be silently swallowed as "the loop closed."
        """
        try:
            bridge_to_queue(loop, queue, event)
            return True
        except RuntimeError as exc:
            logger.debug(f"ExperimentRunner: event loop closed, dropping event ({exc}).")
            return False
