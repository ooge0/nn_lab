"""
Unit tests for :mod:`core.analysis.hallucination_check` -- Layer 2 of the per-response cascade
(CLAUDE.md SS3a). Pins real NLI cross-encoder output on fixed input pairs, per CLAUDE.md SS7's rule
that a metric borrowed from a third-party model still gets a pinned-fixture test.
"""

from core.analysis.hallucination_check import check_hallucination


def test_empty_rag_context_is_not_checked():
    """RAG disabled (empty context) -- there is nothing to check consistency against."""
    result = check_hallucination("Some response text.", "")
    assert result == {"checked": False, "predicted_label": None, "contradiction_score": None}


def test_empty_response_is_not_checked():
    result = check_hallucination("", "Some RAG context.")
    assert result == {"checked": False, "predicted_label": None, "contradiction_score": None}


def test_whitespace_only_inputs_are_not_checked():
    assert check_hallucination("   ", "real context")["checked"] is False
    assert check_hallucination("real response", "   ")["checked"] is False


def test_a_clear_factual_contradiction_is_flagged_as_contradiction():
    context = "The Eiffel Tower is located in Paris, France."
    response = "The Eiffel Tower is in London."
    result = check_hallucination(response, context)
    assert result["checked"] is True
    assert result["predicted_label"] == "contradiction"
    assert result["contradiction_score"] > 0.9


def test_a_consistent_response_is_not_flagged_as_contradiction():
    context = "The Eiffel Tower is located in Paris, France."
    response = "The Eiffel Tower is a famous landmark in Paris."
    result = check_hallucination(response, context)
    assert result["checked"] is True
    assert result["predicted_label"] != "contradiction"
    assert result["contradiction_score"] < 0.1


def test_contradiction_score_is_a_probability_in_zero_one_range():
    result = check_hallucination("Anything.", "Some context.")
    assert 0.0 <= result["contradiction_score"] <= 1.0
