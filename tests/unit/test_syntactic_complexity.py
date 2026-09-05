"""
Unit tests for :mod:`core.analysis.syntactic_complexity` -- pins ``dependency_distance`` on fixed
inputs against real spaCy/TextDescriptives output, per CLAUDE.md SS7's rule that a metric borrowed
from a third-party library still gets its own pinned-fixture test, not just trust that the library
is correct.
"""

from core.analysis.syntactic_complexity import dependency_distance


def test_empty_text_returns_zero():
    assert dependency_distance("") == 0.0
    assert dependency_distance("   ") == 0.0


def test_single_short_token_returns_zero_not_nan():
    """A degenerate one-token input has no dependency relations -- TextDescriptives returns NaN for
    this case; this function must convert that to 0.0, the same 'no signal' convention every other
    metric in this project uses, rather than let a NaN reach a persisted JSONL record."""
    import math

    result = dependency_distance(".")
    assert result == 0.0
    assert not math.isnan(result)


def test_pinned_value_on_a_fixed_sentence():
    """Hand-verified against real spaCy/TextDescriptives output on a fixed sentence -- if this ever
    changes, it means the spaCy model or TextDescriptives version changed the real dependency parse,
    which is exactly the kind of dependency-version drift this pin exists to catch."""
    text = "The quick brown fox jumps over the lazy dog while thinking about philosophy."
    assert dependency_distance(text) == 2.286


def test_longer_more_complex_sentence_scores_higher_than_a_short_simple_one():
    """Directional sanity check: a syntactically deeper sentence should score higher than a trivial
    one -- not pinned to an exact value (a general property, not a fixed-input regression fence)."""
    simple = dependency_distance("The cat sat.")
    complex_sentence = dependency_distance(
        "Although the committee had initially rejected the controversial proposal, "
        "the chairperson, who had privately supported it all along, eventually convinced "
        "the remaining skeptical members to reconsider their position."
    )
    assert complex_sentence > simple


def test_result_is_rounded_to_three_decimals():
    text = "The quick brown fox jumps over the lazy dog while thinking about philosophy."
    result = dependency_distance(text)
    assert result == round(result, 3)
