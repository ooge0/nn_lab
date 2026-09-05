"""
Unit tests for :mod:`core.analysis.calculate_advanced_linguistic_metrics` -- pinning
``semantic_overlap`` (real sentence-embedding cosine similarity) on known-similar/known-dissimilar
text pairs, per CLAUDE.md SS7's "pin expected outputs on known inputs" requirement for borrowed
math. Previously untested: this module had no dedicated test file before this one, despite
computing several metrics persisted on every response.
"""

import pytest

from core.analysis.calculate_advanced_linguistic_metrics import (
    _semantic_similarity,
    calculate_advanced_linguistic_metrics,
)

# --- _semantic_similarity -------------------------------------------------


def test_semantic_similarity_of_identical_text_is_exactly_one():
    """The same string compared to itself has cosine similarity 1.0 (up to floating-point rounding)."""
    assert _semantic_similarity("Hello world", "Hello world") == pytest.approx(1.0, abs=1e-2)


def test_semantic_similarity_of_near_paraphrases_is_high():
    """Two sentences expressing the same idea in different words score a high similarity -- this is the whole point of using embeddings instead of token overlap."""
    score = _semantic_similarity("The cat sat on the mat.", "A cat was sitting on the mat.")
    assert score > 0.8


def test_semantic_similarity_of_unrelated_text_is_low():
    """Two sentences about genuinely unrelated topics score a low similarity, not a coincidentally-inflated one from shared common words alone."""
    score = _semantic_similarity("The cat sat on the mat.", "Stock markets rallied sharply today.")
    assert score < 0.3


def test_semantic_similarity_is_symmetric():
    """Order of the two texts must not change the result -- cosine similarity is inherently symmetric, and the wiring around it shouldn't break that."""
    a = _semantic_similarity("The weather is lovely today.", "It's a beautiful sunny day.")
    b = _semantic_similarity("It's a beautiful sunny day.", "The weather is lovely today.")
    assert a == b


def test_semantic_similarity_returns_zero_for_an_empty_text_not_a_model_call():
    """An empty string on either side returns 0.0 directly -- embedding an empty string isn't a meaningful comparison, and this guard avoids sending one to the model at all."""
    assert _semantic_similarity("", "Hello world") == 0.0
    assert _semantic_similarity("Hello world", "") == 0.0
    assert _semantic_similarity("   ", "Hello world") == 0.0  # whitespace-only counts as empty


def test_semantic_similarity_is_clamped_to_zero_one_range():
    """The returned value never falls outside [0.0, 1.0], even though raw cosine similarity is mathematically defined on [-1.0, 1.0] -- a negative value would break is_echo_response's threshold comparison downstream."""
    score = _semantic_similarity(
        "Completely unrelated topic about aerospace engineering.", "A recipe for chocolate cake."
    )
    assert 0.0 <= score <= 1.0


# --- calculate_advanced_linguistic_metrics (semantic_overlap field specifically) -----------------


def test_semantic_overlap_field_uses_real_similarity_not_token_overlap():
    """
    Regression test for a real bug: this field used to be a plain Jaccard token-set overlap
    despite being named "semantic_overlap" -- found during a wiki audit of what the project's
    metrics actually measure. These two sentences share zero literal words but mean nearly the
    same thing; a token-overlap score would be ~0.0, a real semantic-similarity score should be
    high.
    """
    result = calculate_advanced_linguistic_metrics("The vehicle stopped abruptly.", "The car halted suddenly.", 100.0)
    assert result.semantic_overlap > 0.5


def test_semantic_overlap_field_is_low_for_dissimilar_output():
    """A response that's entirely off-topic from the prompt scores a low semantic_overlap, not an artificially inflated one."""
    result = calculate_advanced_linguistic_metrics(
        "Describe a cat's behavior.", "The stock market crashed today.", 100.0
    )
    assert result.semantic_overlap < 0.3


def test_other_fields_unaffected_by_the_semantic_overlap_fix():
    """levenshtein_dist/expansion_ratio/word_count/unique_ratio are untouched by this fix -- pinned on a fixed input to confirm the surrounding metrics didn't shift."""
    result = calculate_advanced_linguistic_metrics("cat", "cat sat mat", 300.0)
    assert result.word_count == 3
    assert result.unique_ratio == 1.0
    assert result.expansion_ratio == 3.0
    assert result.ms_per_word == 100.0
