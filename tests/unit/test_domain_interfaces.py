"""
Unit tests for the Stage 2 domain interfaces
(:mod:`core.domain.interfaces`) -- confirms each ``Protocol`` is genuinely
checkable at runtime (a conforming fake passes ``isinstance``, a
non-conforming one fails it) rather than trivially satisfied by anything.
"""

from core.domain.entities import ExperimentConfig, GenerationResult, JudgeVerdict, PromptMode, RunRecord
from core.domain.interfaces import KnowledgeBase, LLMClient, Judge, PromptStrategy, Repository


class FakeLLMClient:
    """Minimal conforming LLMClient fake."""

    def generate(self, model, system_prompt, user_prompt, **params) -> GenerationResult:
        return GenerationResult(text="stub", duration_ms=1.0, model=model)


class FakeJudge:
    """Minimal conforming Judge fake."""

    def evaluate(self, response_text, archetype, bias, model) -> JudgeVerdict:
        return JudgeVerdict(verdict=True)


class FakePromptStrategy:
    """Minimal conforming PromptStrategy fake."""

    def build(self, archetype, bias, mode, **kwargs) -> str:
        return f"{archetype}:{bias}:{mode}"


class FakeKnowledgeBase:
    """Minimal conforming KnowledgeBase fake."""

    def retrieve(self, query, top_k=5, archetype=None) -> list:
        return []


class FakeRepository:
    """Minimal conforming Repository fake."""

    def save_run(self, run) -> str:
        return run.run_id

    def save_response(self, run_id, response) -> None:
        pass

    def load_responses(self, run_id=None) -> list:
        return []

    def list_runs(self) -> list:
        return []


class NotAnything:
    """Implements none of the interfaces -- the negative-case control."""

    def unrelated_method(self):
        pass


def test_fake_llm_client_conforms_to_protocol():
    """A class implementing generate(...) satisfies the LLMClient Protocol."""
    assert isinstance(FakeLLMClient(), LLMClient)


def test_fake_judge_conforms_to_protocol():
    """A class implementing evaluate(...) satisfies the Judge Protocol."""
    assert isinstance(FakeJudge(), Judge)


def test_fake_prompt_strategy_conforms_to_protocol():
    """A class implementing build(...) satisfies the PromptStrategy Protocol."""
    assert isinstance(FakePromptStrategy(), PromptStrategy)


def test_fake_knowledge_base_conforms_to_protocol():
    """A class implementing retrieve(...) satisfies the KnowledgeBase Protocol."""
    assert isinstance(FakeKnowledgeBase(), KnowledgeBase)


def test_fake_repository_conforms_to_protocol():
    """A class implementing save_run/save_response/load_responses/list_runs satisfies the Repository Protocol."""
    assert isinstance(FakeRepository(), Repository)


def test_non_conforming_class_fails_every_protocol():
    """A class with none of the required methods fails isinstance for all five interfaces -- the Protocols are not trivially satisfied by anything."""
    other = NotAnything()
    assert not isinstance(other, LLMClient)
    assert not isinstance(other, Judge)
    assert not isinstance(other, PromptStrategy)
    assert not isinstance(other, KnowledgeBase)
    assert not isinstance(other, Repository)


def test_fake_llm_client_returns_generation_result_from_call_shape_matching_legacy_usage():
    """generate() called the way streamlit_app.py's generation call is shaped (model, system_prompt, user_prompt, sampling kwargs) returns a GenerationResult."""
    client = FakeLLMClient()
    result = client.generate(
        "qwen:latest",
        "system prompt",
        "user prompt",
        temperature=0.7,
        top_p=0.9,
        frequency_penalty=1.1,
        presence_penalty=0.2,
        max_tokens=512,
        seed=None,
        json_mode=True,
    )
    assert isinstance(result, GenerationResult)
    assert result.model == "qwen:latest"


def test_judge_verdict_confidence_and_rationale_are_optional():
    """JudgeVerdict can be constructed with only `verdict` -- both other fields stay valid as unset, e.g. for a malformed judge response StructuredJudge can't extract confidence/rationale from."""
    verdict = JudgeVerdict(verdict=False)
    assert verdict.confidence is None
    assert verdict.rationale is None


def test_run_record_round_trips_through_fake_repository():
    """save_run(RunRecord) -> run_id, matching the Repository interface's documented contract."""
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="qwen:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    run = RunRecord(run_id="run-1", started_at="2026-08-21T00:00:00Z", config=config, total_tasks=10)
    repo = FakeRepository()
    assert repo.save_run(run) == "run-1"
