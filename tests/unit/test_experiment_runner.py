"""
Unit tests for :mod:`core.services.experiment_runner` -- ``extract_best_text``
and ``compute_sweep_range`` in isolation, and ``ExperimentRunner`` (Stage 6:
full grid, judge, RAG, sweep, self-critic) against fakes, pinning exact call
shapes and the full persisted entry shape.
"""

import asyncio

from core.domain.entities import ExperimentConfig, GenerationResult, JudgeVerdict, PromptMode, RunRecord
from core.services.experiment_runner import (
    ExperimentRunner,
    TooManyTasksError,
    compute_sweep_range,
    extract_best_text,
)

ARCHETYPES = {
    "common": {
        "intro": "Act as a system for behavioral conditioning.",
        "pre_phrase": "Apply behavioral constraints: ",
        "post_phrase_main": 'Respond ONLY as {"text": "<rewritten output>"}',
        "post_phrase_rules": "No filler, no markdown, no extra keys.",
    },
    "Detached": {"sys_prompt_main": "Enforce emotional coldness.", "about": "Detached archetype description."},
    "Expressive": {
        "sys_prompt_main": "Enforce emotional expressiveness.",
        "about": "Expressive archetype description.",
    },
}


# --- extract_best_text -------------------------------------------------


def test_extract_best_text_from_json_with_text_key():
    """A JSON-object response with a "text" key returns that key's value, not the raw JSON string."""
    assert extract_best_text('{"text": "hello"}') == "hello"


def test_extract_best_text_plain_text_falls_back_to_raw():
    """A response that isn't valid JSON is returned as-is, unchanged."""
    assert extract_best_text("plain prose") == "plain prose"


# --- compute_sweep_range -------------------------------------------------


def test_compute_sweep_range_single_step_returns_v_min():
    """steps <= 1 returns a single-point list at v_min, matching the legacy else-branch."""
    assert compute_sweep_range(0.5, 0.9, steps=1) == [0.5]
    assert compute_sweep_range(0.5, 0.9, steps=0) == [0.5]


def test_compute_sweep_range_linear_interpolation_pinned():
    """Pinned against streamlit_app.py's exact formula (lines 593-594) on a known input."""
    assert compute_sweep_range(0.0, 1.0, steps=5) == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_compute_sweep_range_delta_style_center_plus_minus():
    """A 'Delta' sweep (center=0.7, delta=0.2 -> v_min=0.5, v_max=0.9) matches hand-computed values."""
    assert compute_sweep_range(0.5, 0.9, steps=3) == [0.5, 0.7, 0.9]


def test_compute_sweep_range_descending():
    """ascending=False returns the same interpolated values sorted high-to-low, matching the legacy DESC checkbox."""
    assert compute_sweep_range(0.0, 1.0, steps=3, ascending=False) == [1.0, 0.5, 0.0]


def test_compute_sweep_range_rounds_to_two_decimals():
    """Every interpolated value is rounded to 2 decimals, not left as a raw float division result."""
    values = compute_sweep_range(0.1, 0.2, steps=4)
    assert all(v == round(v, 2) for v in values)


# --- ExperimentRunner ---------------------------------------------------


class FakeLLMClient:
    def __init__(self, response_text='{"text": "styled output"}', delay_seconds: float = 0.0, **result_kwargs):
        self.response_text = response_text
        self.delay_seconds = delay_seconds
        self.result_kwargs = result_kwargs
        self.calls = []

    def generate(self, model, system_prompt, user_prompt, **params):
        self.calls.append(
            {"model": model, "system_prompt": system_prompt, "user_prompt": user_prompt, "params": params}
        )
        if self.delay_seconds:
            import time

            time.sleep(self.delay_seconds)
        return GenerationResult(text=self.response_text, duration_ms=42.0, model=model, **self.result_kwargs)


class FakeRepository:
    def __init__(self):
        self.saved_runs = []
        self.saved_responses = []

    def save_run(self, run: RunRecord) -> str:
        self.saved_runs.append(run)
        return run.run_id

    def save_response(self, run_id, response) -> None:
        self.saved_responses.append((run_id, response))

    def load_responses(self, run_id=None):
        return [r for rid, r in self.saved_responses if run_id is None or rid == run_id]

    def list_runs(self):
        return sorted(self.saved_runs, key=lambda r: r.started_at, reverse=True)


class FakePromptStrategy:
    def __init__(self, prompt="the system prompt"):
        self.prompt = prompt
        self.calls = []

    def build(self, archetype, bias, mode, **kwargs):
        self.calls.append({"archetype": archetype, "bias": bias, "mode": mode, "kwargs": kwargs})
        return self.prompt


class FakeJudge:
    def __init__(self, verdict: bool = True):
        self.verdict = verdict
        self.calls = []

    def evaluate(self, response_text, archetype, bias, model):
        self.calls.append({"response_text": response_text, "archetype": archetype, "bias": bias, "model": model})
        return JudgeVerdict(verdict=self.verdict)


class FakeKnowledgeBase:
    def __init__(self, chunks=None):
        self.chunks = (
            chunks
            if chunks is not None
            else [{"archetype": "Detached", "category": "Behavior", "content": "c", "text": "reference text"}]
        )
        self.calls = []

    def retrieve(self, query, top_k=5, archetype=None):
        self.calls.append({"query": query, "top_k": top_k, "archetype": archetype})
        return self.chunks


def _make_config(**overrides):
    defaults = dict(
        student_models=["qwen:latest"],
        teacher_model="qwen:latest",
        archetypes=["Detached"],
        biases=["formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    defaults.update(overrides)
    return ExperimentConfig(**defaults)


def _make_runner(**kwargs):
    defaults = dict(
        llm_client=FakeLLMClient(),
        repository=FakeRepository(),
        prompt_strategy=FakePromptStrategy(),
        judge=FakeJudge(),
        archetypes=ARCHETYPES,
    )
    defaults.update(kwargs)
    return ExperimentRunner(**defaults)


def _start_and_drain(runner, config):
    async def scenario():
        loop = asyncio.get_running_loop()
        queue = runner.try_start(loop, config)
        assert queue is not None
        events = []
        while True:
            # 20s, not 5s: the real work between progress events runs the full NLTK/textblob/
            # sklearn metrics pipeline, which coverage.py's per-line tracing measurably slows
            # down -- 5s flaked under `pytest --cov` even though the same run is fast uninstrumented.
            event = await asyncio.wait_for(queue.get(), timeout=20.0)
            events.append(event)
            if event.done:
                break
        for _ in range(50):
            if not runner.running:
                break
            await asyncio.sleep(0.02)
        return events

    return asyncio.run(scenario())


def test_compute_total_tasks_multiplies_all_four_dimensions():
    """total_tasks = students x archetypes x biases x sweep_steps -- all four dimensions multiply, not add."""
    config = _make_config(
        student_models=["a", "b"],
        archetypes=["Detached", "Expressive"],
        biases=["x", "y", "z"],
        sweep_param="Temperature",
        sweep_min=0.0,
        sweep_max=1.0,
        sweep_steps=5,
    )
    assert ExperimentRunner.compute_total_tasks(config) == 2 * 2 * 3 * 5


def test_compute_total_tasks_without_sweep_is_one_per_combination():
    """No sweep_param means the sweep dimension collapses to 1 point, not 0 -- a static run still counts as one value per combination."""
    config = _make_config(student_models=["a"], archetypes=["Detached"], biases=["x", "y"])
    assert ExperimentRunner.compute_total_tasks(config) == 2  # 1 student * 1 archetype * 2 biases * 1


def test_try_start_raises_on_missing_teacher_model_when_not_self_critic():
    """teacher_model is required unless self_critic is set -- matches the legacy app's own Teacher validation."""
    runner = _make_runner()
    config = _make_config(teacher_model=None, self_critic=False)

    async def scenario():
        import pytest

        from core.services.experiment_runner import InvalidExperimentConfigError

        loop = asyncio.get_running_loop()
        with pytest.raises(InvalidExperimentConfigError):
            runner.try_start(loop, config)
        assert runner.running is False

    asyncio.run(scenario())


def test_try_start_raises_on_sweep_param_without_resolved_range():
    """A sweep_param set without sweep_min/sweep_max is a misconfigured request, rejected before any generation."""
    runner = _make_runner()
    config = _make_config(sweep_param="Temperature", sweep_min=None, sweep_max=None)

    async def scenario():
        import pytest

        from core.services.experiment_runner import InvalidExperimentConfigError

        loop = asyncio.get_running_loop()
        with pytest.raises(InvalidExperimentConfigError):
            runner.try_start(loop, config)
        assert runner.running is False

    asyncio.run(scenario())


def test_try_start_raises_too_many_tasks_before_touching_the_guard():
    """A config over the max_total_tasks cap is rejected before the concurrent-run guard is engaged -- running stays False, not falsely left True."""
    runner = _make_runner(max_total_tasks=5)
    config = _make_config(biases=["a", "b", "c", "d", "e", "f"])  # 6 tasks > cap of 5

    async def scenario():
        import pytest

        loop = asyncio.get_running_loop()
        with pytest.raises(TooManyTasksError) as exc_info:
            runner.try_start(loop, config)
        assert exc_info.value.total_tasks == 6
        assert exc_info.value.max_total_tasks == 5
        assert runner.running is False  # guard was never engaged

    asyncio.run(scenario())


def test_persists_ollama_performance_fields_and_computes_tokens_per_second():
    """GenerationResult's token counts and Ollama timing breakdown land in the entry unchanged, plus a derived tokens_per_second."""
    repo = FakeRepository()
    runner = _make_runner(
        llm_client=FakeLLMClient(
            '{"text": "We are calm and structured."}',
            prompt_tokens=22,
            completion_tokens=8,
            ollama_total_duration_ms=99.6362,
            ollama_load_duration_ms=3.405,
            ollama_prompt_eval_duration_ms=45.313,
            ollama_eval_duration_ms=40.0,
        ),
        repository=repo,
    )
    config = _make_config()

    _start_and_drain(runner, config)

    _, entry = repo.saved_responses[0]
    assert entry["prompt_tokens"] == 22
    assert entry["completion_tokens"] == 8
    assert entry["ollama_total_duration_ms"] == 99.6362
    assert entry["ollama_load_duration_ms"] == 3.405
    assert entry["ollama_prompt_eval_duration_ms"] == 45.313
    assert entry["ollama_eval_duration_ms"] == 40.0
    assert entry["tokens_per_second"] == 200.0  # 8 tokens / (40.0ms / 1000)


def test_tokens_per_second_is_none_when_ollama_fields_are_unavailable():
    """A backend that can't supply the performance fields (default FakeLLMClient, all None) leaves tokens_per_second None rather than raising ZeroDivisionError/TypeError."""
    repo = FakeRepository()
    runner = _make_runner(llm_client=FakeLLMClient(), repository=repo)
    config = _make_config()

    _start_and_drain(runner, config)

    _, entry = repo.saved_responses[0]
    assert entry["prompt_tokens"] is None
    assert entry["tokens_per_second"] is None


def test_persists_full_entry_shape_with_no_key_collisions():
    """The full entry dict includes generation, judge, RAG, and metrics fields, with the
    self_focus/word_count/ms_per_word collision fix applied (both values survive)."""
    repo = FakeRepository()
    runner = _make_runner(
        llm_client=FakeLLMClient('{"text": "We are calm and structured."}'),
        repository=repo,
    )
    config = _make_config()

    _start_and_drain(runner, config)

    assert len(repo.saved_responses) == 1
    _, entry = repo.saved_responses[0]

    # generation-shape fields
    assert entry["student"] == "qwen:latest"
    assert entry["teacher"] == "qwen:latest"
    assert entry["archetype"] == "Detached"
    assert entry["bias"] == "formal, toxic"
    assert entry["output"] == "We are calm and structured."
    assert entry["strategy"] == "Behavioral conditioning (Tuned)"
    assert entry["archetype_about"] == "Detached archetype description."
    assert entry["sweep_param"] == "Baseline"
    assert entry["val"] == 0.7  # base_temperature, since no sweep

    # judge fields
    assert entry["v_ok"] is True
    assert entry["v_ok_numeric"] == 1

    # RAG fields (disabled)
    assert entry["rag_enabled"] is False
    assert entry["rag_mode"] is None
    assert entry["rag_query"] == ""
    assert entry["rag_chunks_count"] == 0

    # Layer 2 (2026-08-24): not checked when RAG is disabled -- nothing to check consistency against
    assert entry["layer2_checked"] is False
    assert entry["layer2_predicted_label"] is None
    assert entry["layer2_contradiction_score"] is None

    # the collision fix -- both survive, neither silently overwritten
    assert "self_focus" in entry
    assert "self_focus_ext" in entry
    assert "word_count" in entry
    assert "word_count_raw" in entry
    assert "ms_per_word" in entry
    assert "ms_per_word_raw" in entry


def test_self_critic_routes_judge_to_the_student_model():
    """self_critic=True routes the judge call to the student model itself, and persists it under "teacher" too (CLAUDE.md SS4's sycophancy-risk mode)."""
    repo = FakeRepository()
    judge = FakeJudge()
    runner = _make_runner(repository=repo, judge=judge)
    config = _make_config(student_models=["qwen:latest"], self_critic=True, teacher_model=None)

    _start_and_drain(runner, config)

    assert judge.calls[0]["model"] == "qwen:latest"
    _, entry = repo.saved_responses[0]
    assert entry["teacher"] == "qwen:latest"


def test_teacher_student_mode_routes_judge_to_teacher_model():
    """self_critic=False routes the judge call to the configured teacher_model, not the student being evaluated."""
    repo = FakeRepository()
    judge = FakeJudge()
    runner = _make_runner(repository=repo, judge=judge)
    config = _make_config(student_models=["qwen:latest"], teacher_model="phi3:latest", self_critic=False)

    _start_and_drain(runner, config)

    assert judge.calls[0]["model"] == "phi3:latest"


def test_rag_enabled_retrieves_and_injects_context():
    """rag_enabled=True builds the retrieval query from archetype+bias, injects the retrieved chunks into the user prompt, and persists the RAG fields."""
    repo = FakeRepository()
    kb = FakeKnowledgeBase()
    llm = FakeLLMClient()
    runner = _make_runner(repository=repo, knowledge_base=kb, llm_client=llm)
    config = _make_config(rag_enabled=True, rag_mode="Archetype + Bias", rag_top_k=3)

    _start_and_drain(runner, config)

    assert kb.calls[0] == {"query": "Detached formal, toxic", "top_k": 3, "archetype": None}
    _, entry = repo.saved_responses[0]
    assert entry["rag_enabled"] is True
    assert entry["rag_chunks_count"] == 1
    assert "reference text" in entry["rag_context"]
    assert "REFERENCE KNOWLEDGE" in llm.calls[0]["user_prompt"]

    # Layer 2 (2026-08-24): RAG enabled -> real NLI check runs, real score persisted (not gating v_ok)
    assert entry["layer2_checked"] is True
    assert entry["layer2_predicted_label"] in ("contradiction", "entailment", "neutral")
    assert 0.0 <= entry["layer2_contradiction_score"] <= 1.0


def test_rag_disabled_ignores_knowledge_base_even_if_provided():
    """rag_enabled=False never calls the knowledge base, even when one is configured on the runner -- the config flag gates it, not just object presence."""
    repo = FakeRepository()
    kb = FakeKnowledgeBase()
    runner = _make_runner(repository=repo, knowledge_base=kb)
    config = _make_config(rag_enabled=False)

    _start_and_drain(runner, config)

    assert kb.calls == []
    _, entry = repo.saved_responses[0]
    assert entry["rag_context"] == ""


def test_sweep_iterates_the_full_computed_range_and_overrides_one_param():
    """A temperature sweep generates one call per computed value, overriding only that one sampling param while the rest stay at their base values."""
    repo = FakeRepository()
    llm = FakeLLMClient()
    runner = _make_runner(repository=repo, llm_client=llm)
    config = _make_config(sweep_param="Temperature", sweep_min=0.0, sweep_max=1.0, sweep_steps=3)

    _start_and_drain(runner, config)

    assert len(repo.saved_responses) == 3
    temps = [call["params"]["temperature"] for call in llm.calls]
    assert temps == [0.0, 0.5, 1.0]
    # the other sampling params stay at their base values throughout
    assert all(call["params"]["top_p"] == 0.9 for call in llm.calls)
    vals = [entry["val"] for _, entry in repo.saved_responses]
    assert vals == [0.0, 0.5, 1.0]
    sweep_params = [entry["sweep_param"] for _, entry in repo.saved_responses]
    assert sweep_params == ["Temperature", "Temperature", "Temperature"]


def test_full_grid_produces_students_times_archetypes_times_biases_entries():
    """Every (student, archetype) combination is actually generated, not just the count -- checked by the real combo set, not a length assertion alone."""
    repo = FakeRepository()
    runner = _make_runner(repository=repo)
    config = _make_config(
        student_models=["qwen:latest", "phi3:latest"],
        archetypes=["Detached", "Expressive"],
        biases=["formal"],
    )

    _start_and_drain(runner, config)

    assert len(repo.saved_responses) == 4
    combos = {(e["student"], e["archetype"]) for _, e in repo.saved_responses}
    assert combos == {
        ("qwen:latest", "Detached"),
        ("qwen:latest", "Expressive"),
        ("phi3:latest", "Detached"),
        ("phi3:latest", "Expressive"),
    }


def test_second_concurrent_start_is_rejected():
    """A second try_start() call while one run is still in flight returns None instead of starting a competing run -- the single-user concurrent-run guard."""
    runner = _make_runner(llm_client=FakeLLMClient(delay_seconds=0.2))
    config = _make_config()

    async def scenario():
        loop = asyncio.get_running_loop()
        first = runner.try_start(loop, config)
        assert first is not None
        second = runner.try_start(loop, config)
        assert second is None
        while True:
            event = await asyncio.wait_for(first.get(), timeout=5.0)
            if event.done:
                break

    asyncio.run(scenario())


def test_generation_error_emits_error_event_and_clears_guard():
    """A real generation failure (e.g. Ollama unreachable) surfaces as an "error" progress event and releases the concurrent-run guard, rather than hanging the run or leaving `running` stuck True."""

    class FailingLLMClient:
        def generate(self, *args, **kwargs):
            raise RuntimeError("Ollama connection refused")

    repo = FakeRepository()
    runner = _make_runner(llm_client=FailingLLMClient(), repository=repo)

    events = _start_and_drain(runner, _make_config())

    assert events[-1].stage == "error"
    assert "Ollama connection refused" in events[-1].error
    assert repo.saved_responses == []
    assert runner.running is False


# --- request_stop --------------------------------------------------------


def test_request_stop_with_no_run_in_progress_returns_false():
    """Calling request_stop() when nothing is running reports nothing to stop, rather than silently succeeding."""
    runner = _make_runner()
    assert runner.request_stop() is False


def test_request_stop_mid_run_halts_before_the_full_grid_completes():
    """
    request_stop() called after the first response is cooperative, not
    preemptive, and checked only *between* tasks (see `_run`'s loop) --
    a response already in flight when stop is requested still finishes
    and gets persisted, so the exact cutoff point (after task 1, 2, or 3
    of 4) isn't guaranteed. What request_stop() does guarantee, and what
    this pins: the run ends early (fewer than the full grid persisted)
    with a "stopped" terminal event, not "done" -- restores the legacy
    sidebar's "Stop generation" button, dropped during the rewrite.
    """
    repo = FakeRepository()
    llm = FakeLLMClient(
        delay_seconds=0.2
    )  # comfortable margin: the test's own request_stop() call only needs to beat the *next* task's near-instant loop-top check, not this task's delay
    runner = _make_runner(repository=repo, llm_client=llm)
    config = _make_config(archetypes=["Detached", "Expressive"], biases=["formal", "toxic"])  # total_tasks=4

    async def scenario():
        loop = asyncio.get_running_loop()
        queue = runner.try_start(loop, config)
        assert queue is not None

        events = []
        first_generating_seen = False
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=20.0)
            events.append(event)
            if event.stage == "generating" and not first_generating_seen:
                first_generating_seen = True
                runner.request_stop()
            if event.done:
                break
        return events

    events = asyncio.run(scenario())

    assert events[-1].stage == "stopped"
    assert 1 <= events[-1].step < 4  # stopped early -- not all 4 completed
    assert events[-1].total_tasks == 4
    assert 1 <= len(repo.saved_responses) < 4
    assert runner.running is False


def test_stop_requested_flag_is_cleared_by_a_fresh_try_start():
    """A stop flag left set by a previous (stopped) run doesn't leak into and immediately kill the next run."""
    repo = FakeRepository()
    runner = _make_runner(repository=repo, llm_client=FakeLLMClient())
    config = _make_config()

    _start_and_drain(runner, config)  # first run completes normally
    runner._stop_requested.set()  # simulate a stale stop flag from some earlier, already-finished run
    repo.saved_responses.clear()

    events = _start_and_drain(runner, config)

    assert events[-1].stage == "done"
    assert len(repo.saved_responses) == 1


# --- Layer 0 / Layer 1 cascade integration (CLAUDE.md SS3a, SS4/SS6) -----------------------------


def test_layer0_empty_response_skips_judge_and_metrics():
    """A response whose extracted text is blank is rejected by Layer 0 before the judge or any metric computation ever runs -- no wasted judge call, no metric fields in the persisted entry."""
    llm = FakeLLMClient(response_text='{"text": ""}')
    judge = FakeJudge()
    repo = FakeRepository()
    runner = _make_runner(repository=repo, llm_client=llm, judge=judge)

    _start_and_drain(runner, _make_config())

    assert len(judge.calls) == 0  # the judge was never asked to evaluate garbage
    _, entry = repo.saved_responses[0]
    assert entry["layer0_classification"] == "EMPTY"
    assert entry["v_ok"] is False
    assert entry["v_ok_numeric"] == 0
    assert "sentiment" not in entry  # metrics computation was skipped entirely
    assert "coherence" not in entry


def test_layer0_malformed_response_skips_judge_and_metrics():
    """A response that isn't valid JSON at all (and doesn't look cut off) is classified MALFORMED_JSON and rejected the same way as an empty one."""
    llm = FakeLLMClient(response_text="The model ignored the JSON instruction entirely and just chatted.")
    judge = FakeJudge()
    repo = FakeRepository()
    runner = _make_runner(repository=repo, llm_client=llm, judge=judge)

    _start_and_drain(runner, _make_config())

    assert len(judge.calls) == 0
    _, entry = repo.saved_responses[0]
    assert entry["layer0_classification"] == "MALFORMED_JSON"
    assert entry["v_ok"] is False


def test_layer1_echo_response_skips_judge_call_but_still_computes_metrics():
    """
    A response that echoes its own bias instruction back (real failure pattern, CLAUDE.md SS0's
    7/125 finding) is caught by Layer 1 and never reaches the judge -- but Layer 1 runs *after*
    metrics computation (it reuses semantic_overlap), so metric fields are still present, unlike
    a Layer 0 rejection.
    """
    llm = FakeLLMClient(response_text='{"text": "Personalization, formal, toxic."}')
    judge = FakeJudge()
    repo = FakeRepository()
    runner = _make_runner(repository=repo, llm_client=llm, judge=judge)
    config = _make_config(biases=["personalization, formal, toxic"])

    _start_and_drain(runner, config)

    assert len(judge.calls) == 0  # Layer 1 rejected it before the judge was ever called
    _, entry = repo.saved_responses[0]
    assert entry["layer0_classification"] == "VALID"
    assert entry["layer1_echo_detected"] is True
    assert entry["v_ok"] is False
    assert entry["v_rationale"] is not None and "echo" in entry["v_rationale"].lower()
    assert "sentiment" in entry  # metrics WERE computed, unlike a Layer 0 rejection


def test_genuine_substantive_response_reaches_the_real_judge():
    """A real, substantive, non-echo response passes both Layer 0 and Layer 1 and reaches the actual judge -- the cascade doesn't reject legitimate content."""
    llm = FakeLLMClient(
        response_text=(
            '{"text": "It seems to me, without proper verification, that your intentions in this '
            'matter might be concealing more than you are willing to admit, and I remain cautious."}'
        )
    )
    judge = FakeJudge(verdict=True)
    repo = FakeRepository()
    runner = _make_runner(repository=repo, llm_client=llm, judge=judge)
    config = _make_config(biases=["personalization, formal, toxic"])

    _start_and_drain(runner, config)

    assert len(judge.calls) == 1  # the real judge was actually consulted
    _, entry = repo.saved_responses[0]
    assert entry["layer0_classification"] == "VALID"
    assert entry["layer1_echo_detected"] is False
    assert entry["v_ok"] is True
