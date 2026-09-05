"""
Unit tests for :func:`web.plotting.benchmark_charts.build_benchmark_view` -- specifically the
``/benchmark`` leaderboard's ``final_score`` formula, pinned directly against a small synthetic
DataFrame rather than only observed indirectly through rendered HTML (the existing
``tests/integration/test_benchmark_api.py`` coverage). Written alongside two real bugs found and
fixed 2026-08-24 in the same block of code -- see ``web/plotting/benchmark_charts.py``'s own inline
comments and ``docs/source/wiki/04-llm-analytics.rst``'s "A metric that contradicted itself" section
for the full story:

1. The leaderboard used to weight a ``mimicry_score`` derived from ``semantic_overlap`` -- a field
   that measures similarity to the bias/archetype *label*, not to any teacher response, and which
   the Layer 1 echo-detection cascade (``core/analysis/response_classification.py``) rejects
   responses for when it is *high*. The leaderboard was rewarding the same behavior the cascade
   flags as a failure. Removed, not replaced with a different unvalidated proxy.
2. The pass-rate component aggregated ``v_ok_numeric`` from ``df_valid`` (already filtered to
   ``v_ok == 1``), whose mean is trivially always 1.0 for any student with at least one passing
   response -- a real 50% pass rate and a real 100% pass rate scored identically. Fixed to use the
   real, un-filtered per-student mean.
"""

import pandas as pd

from web.plotting.benchmark_charts import build_benchmark_view


def _row(student, v_ok, coherence, ms_per_word, semantic_overlap=0.9):
    """One response record with every column build_benchmark_view requires -- semantic_overlap is
    deliberately set high (0.9, in Layer 1's echo range) to prove it no longer affects the score."""
    return {
        "student": student,
        "teacher": "llama3:latest",
        "output": f"{student}-{v_ok}-{coherence}",
        "word_count": 10,
        "v_ok": v_ok,
        "v_ok_numeric": v_ok,
        "ms_per_word": ms_per_word,
        "duration_ms": 100.0,
        "coherence": coherence,
        "semantic_overlap": semantic_overlap,
    }


def test_leaderboard_final_score_matches_the_documented_formula_exactly():
    """final_score = 0.4*pass_rate + 0.3*coherence + 0.3*speed_score, hand-computed on a fixed input."""
    df = pd.DataFrame(
        [
            _row("A", 1, coherence=0.8, ms_per_word=10),
            _row("A", 0, coherence=0.8, ms_per_word=10),
            _row("B", 1, coherence=0.2, ms_per_word=100),
        ]
    )

    result = build_benchmark_view(df)

    table = result["leaderboard_table"]
    # pass_rate: A = 1/2 = 0.5 (real, un-filtered rate); B = 1/1 = 1.0
    # speed_score: max_ms=100 -> A=(100-10)/100=0.9, B=(100-100)/100=0.0
    # final_score: A = 0.5*0.4 + 0.8*0.3 + 0.9*0.3 = 0.71; B = 1.0*0.4 + 0.2*0.3 + 0.0*0.3 = 0.46
    assert "0.71" in table
    assert "0.46" in table
    assert result["champion"] == "A"


def test_leaderboard_pass_rate_is_not_trivially_always_one():
    """Regression test for the df_valid-mean bug: a 50% and a 100% pass rate must differ in the table."""
    df = pd.DataFrame(
        [
            _row("HalfPass", 1, coherence=0.5, ms_per_word=50),
            _row("HalfPass", 0, coherence=0.5, ms_per_word=50),
            _row("FullPass", 1, coherence=0.5, ms_per_word=50),
        ]
    )

    result = build_benchmark_view(df)

    table = result["leaderboard_table"]
    assert "0.5" in table  # HalfPass's real pass rate
    assert result["champion"] == "FullPass"  # strictly better pass rate, identical coherence/speed


def test_leaderboard_no_longer_contains_mimicry_score_or_semantic_overlap():
    """Regression test for the removed field: neither name should appear in the rendered table at all."""
    df = pd.DataFrame([_row("A", 1, coherence=0.8, ms_per_word=10, semantic_overlap=0.99)])

    result = build_benchmark_view(df)

    table = result["leaderboard_table"]
    assert "mimicry_score" not in table
    assert "mimicry" not in table.lower()
    assert "semantic_overlap" not in table
