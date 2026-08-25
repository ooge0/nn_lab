"""
Unit tests for :class:`core.analysis.neuro_metrics.NeuroMetrics` -- pinning ``cognitive_load`` on
hand-computed fixed inputs per CLAUDE.md SS7's "pin expected outputs on known inputs" requirement.
Previously untested: this module had no dedicated test file before this one, despite computing
several metrics persisted on every response.
"""

import pytest

from core.analysis.neuro_metrics import NeuroMetrics


@pytest.fixture
def neuro():
    """``NeuroMetrics`` doesn't touch ``sia`` inside ``cognitive_load`` -- ``None`` is safe for these tests."""
    return NeuroMetrics(sia=None)


def test_cognitive_load_on_a_short_plain_sentence_pinned_by_hand(neuro):
    """
    One 4-word sentence, one subordinator ("because"), one punctuation character (the
    trailing period) -- every component hand-computed:
    avg_sentence_len_norm = min(4/40, 1.0) = 0.1
    punctuation_density_norm = min(1 char / 4 words, 1.0) = 0.25
    sub_ratio = 1 subordinator / 4 words = 0.25
    cognitive_load = (0.1 + 0.25 + 0.25) / 3 = 0.2
    """
    words = ["because", "the", "cat", "sat"]
    sentences = ["Because the cat sat."]
    text = "Because the cat sat."

    result = neuro.cognitive_load(words, sentences, text)

    assert result == pytest.approx(0.2, abs=1e-6)


def test_cognitive_load_sentence_length_saturates_at_the_cap(neuro):
    """
    A single 80-word "sentence" exceeds the 40-word normalization cap, so
    avg_sentence_len_norm saturates at 1.0 rather than growing unbounded -- with no punctuation
    and no subordinators, cognitive_load = (1.0 + 0 + 0) / 3 = 1/3.
    """
    words = ["word"] * 80
    sentences = ["s"]  # one sentence -> avg_sentence_len = 80/1 = 80, well past the cap of 40
    text = ""  # no punctuation characters

    result = neuro.cognitive_load(words, sentences, text)

    assert result == pytest.approx(1 / 3, abs=1e-6)


def test_cognitive_load_all_three_components_contribute_not_just_sentence_length(neuro):
    """
    Regression test for the real normalization bug: before normalization, sentence length's raw
    magnitude (commonly 5-30+) dominated punctuation/subordinator density (both already ~[0,1]),
    making the composite nearly insensitive to them. Two texts with identical, short sentence
    length but very different punctuation/subordinator content must now produce different
    cognitive_load values -- if they came out equal, the fix wouldn't actually be normalizing.
    """
    low = neuro.cognitive_load(["the", "cat", "sat"], ["The cat sat"], "The cat sat")
    high = neuro.cognitive_load(
        ["although", "the", "cat", "sat"], ["Although the cat sat!!!"], "Although the cat sat!!!"
    )

    assert high > low


def test_cognitive_load_returns_zero_for_empty_input(neuro):
    """No words or no sentences short-circuits to 0 rather than dividing by zero."""
    assert neuro.cognitive_load([], [], "") == 0
    assert neuro.cognitive_load(["word"], [], "word") == 0


def test_cognitive_load_never_exceeds_one():
    """
    Even a pathological input (very long single sentence, extremely heavy punctuation, every
    word a subordinator) stays within [0, 1] -- each of the three normalized components is
    individually capped, so their average can't exceed 1.0.
    """
    neuro = NeuroMetrics(sia=None)
    words = ["because"] * 50
    sentences = ["s"]
    text = "!" * 500

    result = neuro.cognitive_load(words, sentences, text)

    assert 0.0 <= result <= 1.0
