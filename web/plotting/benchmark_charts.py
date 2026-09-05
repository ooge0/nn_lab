"""
web.plotting.benchmark_charts
================================

Stage 12 presentation -- ``streamlit_app.py``'s "LLM benchmark report" tab
(``streamlit_app.py:3026-3178``). Pure aggregation over one run's already-
persisted responses, no new metric computation -- the same "read-only over
Stages 6-7's data" pattern Stage 7's ``MetricsEngine`` and Stage 8's
``analytics_charts`` already established. Kept as plain functions here
(like Stage 8), not a separate ``core/services`` module, since it's
straightforward pandas aggregation with no algorithm worth unit-pinning in
isolation from the charts themselves.
"""

import pandas as pd
import plotly.express as px

from web.plotting.render import figure_to_div

TEMPLATE = "plotly_white"

_REQUIRED_COLUMNS = {"student", "teacher", "output", "word_count", "v_ok", "v_ok_numeric", "ms_per_word", "duration_ms"}


def build_benchmark_view(df: pd.DataFrame) -> "dict | None":
    """
    Build the full benchmark report for one run's responses.

    Parameters
    ----------
    df : pandas.DataFrame
        One run's responses, via ``pandas.json_normalize`` (matching the
        legacy tab's own plain, un-bridged DataFrame -- confirmed by
        reading ``streamlit_app.py`` directly, the same data path Stage 8
        and Stage 10 use, not :class:`~core.analysis.data_contract
        .LabDataBridge`).

    Returns
    -------
    dict or None
        ``None`` if any of the core columns every section below depends on
        (student/teacher/word_count/v_ok/v_ok_numeric/ms_per_word/
        duration_ms) is missing -- e.g. a sparse pre-Stage-5 run, the same
        real failure mode Stage 8 found and guarded against. Otherwise a
        dict with ``overview`` (counts), ``success_chart``, ``perf_chart``,
        ``quality_chart`` (``None`` if none of its columns are present,
        matching the legacy tab's own ``existing_quality`` guard exactly),
        ``psycho_chart`` (same, ``existing_psy``), ``leaderboard_table``
        (HTML), ``champion`` (best model name, or ``None`` if the
        leaderboard is empty).
    """
    if not _REQUIRED_COLUMNS.issubset(df.columns):
        return None

    df_clean = df[df["word_count"] > 0]
    df_valid = df_clean[df_clean["v_ok"] == 1].drop_duplicates(subset=["output", "student", "teacher"])

    overview = {
        "total_samples": len(df),
        "valid_samples": len(df_valid),
        "unique_students": df_valid["student"].nunique(),
        "unique_teachers": df_valid["teacher"].nunique(),
    }

    success_df = df_clean.groupby("student")["v_ok_numeric"].mean().sort_values(ascending=False).reset_index()
    success_fig = px.bar(
        success_df,
        x="student",
        y="v_ok_numeric",
        title="Pass rate (%) by model (v_ok_numeric)",
        labels={"v_ok_numeric": "Success probability", "student": "Model Name"},
        template=TEMPLATE,
        color="v_ok_numeric",
        color_continuous_scale="RdYlGn",
    )

    perf_df = df_valid.groupby("student")[["ms_per_word", "duration_ms"]].mean().reset_index()
    perf_fig = px.bar(
        perf_df,
        x="student",
        y="ms_per_word",
        title="Inference speed (Lower is better)",
        labels={"ms_per_word": "Latency (ms/word)"},
        template=TEMPLATE,
    )

    quality_chart = None
    quality_cols = ["coherence", "cognitive_load", "lexical_density", "semantic_overlap", "expansion_ratio"]
    existing_quality = [c for c in quality_cols if c in df_valid.columns]
    if existing_quality:
        quality_df = df_valid.groupby("student")[existing_quality].mean().reset_index()
        quality_fig = px.imshow(
            quality_df.set_index("student"),
            text_auto=".3f",
            title="Avg quality scores per model",
            color_continuous_scale="Viridis",
            template=TEMPLATE,
        )
        quality_chart = figure_to_div(quality_fig)

    psycho_chart = None
    psycho_cols = ["self_focus", "modality", "cognitive_density", "abstract_ratio", "repetition_score"]
    existing_psy = [c for c in psycho_cols if c in df_valid.columns]
    if existing_psy:
        psycho_df = df_valid.groupby("student")[existing_psy].mean().reset_index()
        psycho_fig = px.bar(
            psycho_df,
            x="student",
            y=existing_psy,
            barmode="group",
            title="Linguistic trait distribution",
            template=TEMPLATE,
        )
        psycho_chart = figure_to_div(psycho_fig)

    leaderboard = None
    champion = None
    if {"coherence"}.issubset(df_valid.columns) and not df_valid.empty:
        leaderboard = (
            df_valid.groupby("student")
            .agg(
                coherence=("coherence", "mean"),
                ms_per_word=("ms_per_word", "mean"),
            )
            .reset_index()
        )
        # Found and fixed alongside the mimicry_score removal below: this used to aggregate
        # v_ok_numeric from df_valid (already filtered to v_ok == 1), whose mean is trivially
        # always 1.0 for every student that has at least one passing response -- a model with a
        # real 50% pass rate and one with 100% scored identically here. Pass rate is now the real,
        # un-filtered per-student mean over df_clean (matching success_chart's own aggregation a
        # few lines above, which already did this correctly), then joined onto the coherence/speed
        # columns above, which are legitimately only meaningful over valid responses.
        pass_rate = df_clean.groupby("student")["v_ok_numeric"].mean()
        leaderboard["v_ok_numeric"] = leaderboard["student"].map(pass_rate)
        max_ms = leaderboard["ms_per_word"].max()
        leaderboard["speed_score"] = (max_ms - leaderboard["ms_per_word"]) / max_ms if max_ms else 0.0
        # Fixed 2026-08-24: this used to also weight a "mimicry_score" derived from
        # semantic_overlap (student output vs. the terse bias/archetype label, not vs. a teacher
        # response -- no field anywhere actually compares one model's output to another's for the
        # same prompt, see wiki/04-llm-analytics.rst's "Cross-response / model-comparison level"
        # section). Worse, semantic_overlap is the exact field Layer 1 (core/analysis/
        # response_classification.py::is_echo_response) rejects responses for when it's HIGH --
        # this leaderboard was rewarding models for the same behavior the cascade flags as a
        # failure. Removed rather than replaced with a different (still-unvalidated) proxy;
        # rebalanced across the three real, validated signals instead of inventing a fourth.
        leaderboard["final_score"] = (
            leaderboard["v_ok_numeric"] * 0.4 + leaderboard["coherence"] * 0.3 + leaderboard["speed_score"] * 0.3
        )
        leaderboard = leaderboard.sort_values("final_score", ascending=False).reset_index(drop=True)
        if not leaderboard.empty:
            champion = leaderboard.iloc[0]["student"]

    return {
        "overview": overview,
        "success_chart": figure_to_div(success_fig),
        "perf_chart": figure_to_div(perf_fig),
        "quality_chart": quality_chart,
        "psycho_chart": psycho_chart,
        "leaderboard_table": leaderboard.to_html(index=False) if leaderboard is not None else None,
        "champion": champion,
    }
