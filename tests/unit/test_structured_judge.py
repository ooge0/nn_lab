"""
Unit tests for :class:`core.adapters.structured_judge.StructuredJudge` -- replaces
``tests/unit/test_naive_judge.py`` (deleted alongside ``core/adapters/naive_judge.py``) now that
CLAUDE.md SS4/SS6's author-swap boundary has been crossed by explicit author decision, not a
default "AI-agent improves whatever it finds" change. Covers real JSON parsing (the fix), the
malformed-response fallback (now distinguishable from a genuine "no" via ``rationale``, unlike the
old substring-matching bug), and confirms the request shape still asks the model for structured
JSON.
"""

from core.adapters.structured_judge import StructuredJudge
from tests.unit.test_experiment_runner import FakeLLMClient


def test_clear_pass_is_parsed_from_real_json():
    """A well-formed judge response is genuinely parsed, not substring-matched -- verdict/confidence/rationale all come from the real JSON fields."""
    llm = FakeLLMClient(
        response_text='{"verdict": true, "confidence": 0.92, "rationale": "Matches the Detached archetype: cold, minimal engagement."}'
    )
    judge = StructuredJudge(llm)

    verdict = judge.evaluate("some generated text", "Detached", "formal, toxic", "qwen:latest")

    assert verdict.verdict is True
    assert verdict.confidence == 0.92
    assert verdict.rationale == "Matches the Detached archetype: cold, minimal engagement."


def test_clear_fail_is_parsed_from_real_json():
    """A well-formed 'no' verdict is parsed the same way as a 'yes' -- verdict=False isn't a fallback state here, it's a real judgment."""
    llm = FakeLLMClient(
        response_text='{"verdict": false, "confidence": 0.85, "rationale": "Response is warm and engaged, not detached."}'
    )
    judge = StructuredJudge(llm)

    verdict = judge.evaluate("some generated text", "Detached", "formal, toxic", "qwen:latest")

    assert verdict.verdict is False
    assert verdict.confidence == 0.85
    assert verdict.rationale == "Response is warm and engaged, not detached."


def test_malformed_json_response_falls_back_to_a_distinguishable_false():
    """
    A garbled, non-JSON response resolves to verdict=False -- but unlike the old
    NaiveJudge's identical-looking failure, this is now distinguishable from a genuine "no" by
    reading `rationale`, which explains it's a parse failure, not a real judgment.
    """
    judge = StructuredJudge(FakeLLMClient(response_text="<html>502 Bad Gateway</html>"))

    verdict = judge.evaluate("some generated text", "Detached", "formal, toxic", "qwen:latest")

    assert verdict.verdict is False
    assert verdict.confidence == 0.0
    assert verdict.rationale is not None and "not valid JSON" in verdict.rationale


def test_valid_json_missing_verdict_key_falls_back_cleanly():
    """Valid JSON that's missing the required 'verdict' key is still a malformed-response fallback, not a crash."""
    judge = StructuredJudge(FakeLLMClient(response_text='{"confidence": 0.5}'))

    verdict = judge.evaluate("some generated text", "Detached", "formal, toxic", "qwen:latest")

    assert verdict.verdict is False
    assert verdict.rationale is not None and "verdict" in verdict.rationale


def test_confidence_outside_zero_one_range_is_clamped():
    """A judge model returning an out-of-range confidence (e.g. 1.5, or a raw percentage like 92) is clamped to [0, 1] rather than persisted as a nonsensical value."""
    judge = StructuredJudge(
        FakeLLMClient(response_text='{"verdict": true, "confidence": 1.5, "rationale": "very sure"}')
    )

    verdict = judge.evaluate("text", "Detached", "formal", "qwen:latest")

    assert verdict.confidence == 1.0


def test_missing_confidence_and_rationale_stay_none_not_defaulted():
    """A judge response with only 'verdict' (no confidence/rationale) leaves those fields None -- not silently defaulted to a fake 0.0/empty-string value that would look like real data."""
    judge = StructuredJudge(FakeLLMClient(response_text='{"verdict": true}'))

    verdict = judge.evaluate("text", "Detached", "formal", "qwen:latest")

    assert verdict.verdict is True
    assert verdict.confidence is None
    assert verdict.rationale is None


def test_judge_model_varies_per_call_for_self_critic_mode():
    """The judge model is a per-call parameter, not fixed at construction -- supports self-critic (judge=student) and teacher-student (judge=teacher_model) routing from the same StructuredJudge instance."""
    llm = FakeLLMClient(response_text='{"verdict": true, "confidence": 0.9, "rationale": "ok"}')
    judge = StructuredJudge(llm)

    judge.evaluate("text", "Detached", "formal", "qwen:latest")
    judge.evaluate("text", "Detached", "formal", "llama3:latest")

    assert llm.calls[0]["model"] == "qwen:latest"
    assert llm.calls[1]["model"] == "llama3:latest"


def test_request_asks_for_structured_json_mode():
    """The request sets json_mode=True and includes the archetype/bias/response text -- confirms the request shape, independent of how the response gets parsed."""
    llm = FakeLLMClient(response_text='{"verdict": true, "confidence": 0.9, "rationale": "ok"}')
    judge = StructuredJudge(llm)

    judge.evaluate("the generated text", "Detached", "formal, toxic", "qwen:latest")

    call = llm.calls[0]
    assert call["params"].get("json_mode") is True
    assert "Detached" in call["user_prompt"]
    assert "formal, toxic" in call["user_prompt"]
    assert "the generated text" in call["user_prompt"]
