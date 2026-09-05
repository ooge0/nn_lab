"""
Unit tests for :class:`core.analysis.nlp_science.PsychScientist` -- pins
``zipf_deviation`` on fixed strings with hand-computed expected values
(CLAUDE.md SS7: don't assume a borrowed metric is correct, pin outputs on
known inputs so a dependency/logic change surfaces as a failing test). This
closes the gap flagged in the QA traceability matrix (R9): the linguistic
metrics used in production had only indirect coverage via the full
entry-shape test, never a direct pinned test against a fixed input.
"""

import math

import pytest

from core.analysis.nlp_science import PsychScientist


@pytest.fixture(scope="module")
def scientist():
    return PsychScientist()


def test_zipf_deviation_pinned_on_a_hand_computed_distribution(scientist):
    """
    "a a a b b c" -> word frequencies {a:3, b:2, c:1}, ranks [1,2,3].
    Zipf-expected frequencies (C=3, C/rank): [3.0, 1.5, 1.0].
    RMSE of [3,2,1] vs [3.0,1.5,1.0] = sqrt(mean([0, 0.25, 0])) = sqrt(1/12).
    Normalized by max observed frequency (3): sqrt(1/12) / 3.
    """
    expected = math.sqrt(1 / 12) / 3
    assert scientist.zipf_deviation("a a a b b c") == pytest.approx(expected, abs=1e-9)


def test_zipf_deviation_on_text_with_no_alphabetic_words_is_zero(scientist):
    """A string with no alphabetic tokens (only punctuation/numbers) returns 0.0 rather than dividing by zero."""
    assert scientist.zipf_deviation("123 456 !!! ???") == 0.0


def test_zipf_deviation_on_empty_string_is_zero(scientist):
    """An empty string returns 0.0, matching the no-words guard."""
    assert scientist.zipf_deviation("") == 0.0


def test_zipf_deviation_is_non_negative(scientist):
    """zipf_deviation is an RMSE-based score, normalized -- always >= 0 for any real text."""
    score = scientist.zipf_deviation("The quick brown fox jumps over the lazy dog. The dog barks.")
    assert score >= 0.0


# --- social_focus (added 2026-08-24) -----------------------------------------------------


def test_social_focus_contrasts_with_self_focus_on_a_symmetric_sentence(scientist):
    """8 words, 2 self-pronouns (i, we) and 2 social-pronouns (you, your) -- both ratios pinned equal by construction."""
    result = scientist.analyze_text("I told you that we appreciate your help.")
    assert result["self_focus"] == 0.25
    assert result["social_focus"] == 0.25


def test_social_focus_is_zero_when_no_social_pronouns_present(scientist):
    result = scientist.analyze_text("I think we should decide now.")
    assert result["social_focus"] == 0.0


# --- hedge_ratio / booster_ratio (added 2026-08-24, Hyland 2005 metadiscourse categories) --------


def test_hedge_ratio_pinned_on_a_fixed_sentence(scientist):
    """9 words, 3 hedge words (might, possibly, could) -> 3/9."""
    result = scientist.analyze_text("This might possibly work but it could also fail.")
    assert result["hedge_ratio"] == 0.333
    assert result["booster_ratio"] == 0.0


def test_booster_ratio_pinned_on_a_fixed_sentence(scientist):
    """7 words, 2 booster words (definitely, absolutely) -> 2/7."""
    result = scientist.analyze_text("This is definitely true and absolutely certain.")
    assert result["booster_ratio"] == 0.286
    assert result["hedge_ratio"] == 0.0


def test_hedge_and_booster_ratio_are_zero_on_empty_text(scientist):
    result = scientist.analyze_text("")
    assert result["hedge_ratio"] == 0
    assert result["booster_ratio"] == 0
    assert result["social_focus"] == 0
