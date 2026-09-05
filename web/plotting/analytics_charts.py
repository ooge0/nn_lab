"""
web.plotting.analytics_charts
================================

Stage 8's three ``tab_analytics`` sub-tabs, ported from
``streamlit_app.py:1182-1357`` and ``tmp/simple_plotty_staff.py``'s
``get_high_dim_dashboard`` (relocated here). Pure presentation over a
DataFrame built from a run's already-persisted responses -- no new metric
computation; every column referenced here is already produced by
:meth:`core.services.experiment_runner.ExperimentRunner._run_one`.

One deliberate simplification from the legacy code: the Levenshtein-distance
chart's ``color_col`` selection branched on ``sweep_param`` across four
near-identical cases (all resolving to ``"val"``), with a fallback to
``val_temperature`` for the "Baseline" (no-sweep) case specifically. The
current entry shape *does* still persist ``val_temperature`` (the
configured base temperature, unconditionally) -- but in the one case that
fallback branch covers, ``val`` already equals ``val_temperature`` (
:class:`~core.services.experiment_runner.ExperimentRunner` sets
``val = base_temperature`` whenever nothing was swept), so the branch has
nothing left to decide either way. Collapsed to just ``"val"``.

A "Real generation speed (tokens/sec)" chart (Adherence & metrics sub-tab)
uses ``tokens_per_second`` -- a genuine measurement from Ollama's own
per-call timing (``completion_tokens`` / ``ollama_eval_duration_ms``),
computed in ``ExperimentRunner._run_one``, not the ``ms_per_word`` proxy
every other chart here still uses (word count over wall-clock duration).
Both are kept: ``ms_per_word`` stays meaningful for any future non-Ollama
backend that can't report real per-call token timing; ``tokens_per_second``
is the accurate one specifically for Ollama-backed runs today.
"""

import pandas as pd
import plotly.express as px

from web.plotting.render import QUALITATIVE_PALETTE, figure_to_div

TEMPLATE = "plotly_white"


def _add_if_present(
    charts: "list[tuple[str, str]]", df: pd.DataFrame, required: "list[str]", title: str, build
) -> None:
    """
    Append ``(title, html)`` to ``charts`` only if every column in
    ``required`` exists on ``df``.

    Notes
    -----
    Added after a real (not fictional) run on disk -- an early, sparse
    export predating Stage 6's full field set (only ``student``,
    ``archetype``, ``bias``, ``duration_ms``, ``output``) -- crashed this
    whole sub-tab with a 500 when ``px.bar``/``px.line`` referenced a column
    that simply wasn't there. Unlike the legacy Streamlit code (which never
    guarded most of these charts and would have crashed identically on the
    same data), real persisted data isn't guaranteed to have every field
    Stage 6 introduces, so each chart here degrades gracefully instead of
    assuming the column set is fixed.
    """
    if all(col in df.columns for col in required):
        charts.append((title, figure_to_div(build())))


def build_adherence_charts(df: pd.DataFrame) -> "list[tuple[str, str]]":
    """
    Sub-tab 1 -- Adherence & metrics.

    Parameters
    ----------
    df : pandas.DataFrame
        One run's responses, ``pandas.json_normalize``-flattened.

    Returns
    -------
    list[tuple[str, str]]
        ``(title, html)`` pairs, in display order -- a chart is simply
        omitted (not an error) if its required columns aren't present.
    """
    charts: "list[tuple[str, str]]" = []

    if "val" in df.columns and "v_ok_numeric" in df.columns:
        pivot = df.pivot_table(index="student", columns="val", values="v_ok_numeric", aggfunc="mean", fill_value=0)
        fig = px.imshow(
            pivot,
            color_continuous_scale="RdYlGn",
            text_auto=".0%",
            aspect="auto",
            title="Adherence heatmap (by parameter)",
            template=TEMPLATE,
        )
        charts.append(("Adherence heatmap (by parameter)", figure_to_div(fig)))

    _add_if_present(
        charts,
        df,
        ["student"],
        "Workload distribution",
        lambda: px.pie(df, names="student", title="Workload distribution", template=TEMPLATE),
    )

    _add_if_present(
        charts,
        df,
        ["student", "duration_ms"],
        "Latency (ms)",
        lambda: px.box(df, x="student", y="duration_ms", color="student", title="Latency (ms)", template=TEMPLATE),
    )
    _add_if_present(
        charts,
        df,
        ["student", "ms_per_word"],
        "Generation velocity (ms/word)",
        lambda: px.line(df, y="ms_per_word", color="student", title="Generation velocity (ms/word)", template=TEMPLATE),
    )
    _add_if_present(
        charts,
        df,
        ["student", "tokens_per_second"],
        "Real generation speed (tokens/sec)",
        lambda: px.box(
            df,
            x="student",
            y="tokens_per_second",
            color="student",
            title="Real generation speed (tokens/sec, from Ollama's own timing)",
            template=TEMPLATE,
        ),
    )

    _add_if_present(
        charts,
        df,
        ["student", "word_count"],
        "Word count consistency",
        lambda: px.line(
            df, y="word_count", color="student", markers=True, title="Word count consistency", template=TEMPLATE
        ),
    )
    _add_if_present(
        charts,
        df,
        ["student", "unique_ratio"],
        "Vocabulary diversity ratio",
        lambda: px.bar(
            df, x="student", y="unique_ratio", color="student", title="Vocabulary diversity ratio", template=TEMPLATE
        ),
    )

    _add_if_present(
        charts,
        df,
        ["student", "levenshtein_dist", "val"],
        "Levenshtein distance to prompt/bias",
        lambda: px.bar(
            df,
            x="student",
            y="levenshtein_dist",
            color="val",
            barmode="group",
            title="Levenshtein distance to prompt/bias",
            template=TEMPLATE,
        ),
    )
    _add_if_present(
        charts,
        df,
        ["student", "semantic_overlap"],
        "Semantic alignment overlap",
        lambda: px.line(
            df, y="semantic_overlap", color="student", title="Semantic alignment overlap", template=TEMPLATE
        ),
    )

    # word_count is only computed for Layer-0-VALID responses (ExperimentRunner._run_one skips
    # metrics computation entirely for a rejected response) -- a run with even one rejected
    # response has a real (present) but partially-NaN word_count column, which _add_if_present's
    # column-existence check doesn't catch. Most charts tolerate a NaN value (a line chart just
    # shows a gap), but Plotly's marker `size` validator rejects NaN outright and crashes the whole
    # page -- confirmed via a real 500 on a live run with 3/500 TRUNCATED responses. Filtered here,
    # scoped to this one chart, rather than loosening _add_if_present's existence check for every
    # chart (most don't need it).
    _add_if_present(
        charts,
        df,
        ["punc_density", "expansion_ratio", "archetype", "student", "word_count"],
        "Psycholinguistic signature",
        lambda: px.scatter(
            df.dropna(subset=["word_count"]),
            x="punc_density",
            y="expansion_ratio",
            color="archetype",
            symbol="student",
            size="word_count",
            title="Style distribution (raw space)",
            template=TEMPLATE,
        ),
    )

    # Added 2026-08-24: "strategy" (the PromptStrategy mode -- Tuned/Behavioral, Blind, Raw) is
    # persisted on every response but had never been used as a chart grouping dimension anywhere
    # (confirmed by grep before adding this -- zero hits across web/plotting/*.py). Answers "does
    # prompt structure affect stability": pass-rate as a mean (does the mode change *whether* the
    # model complies) and coherence as a spread (does the mode change how *consistent* compliant
    # responses are), the same mean-vs-spread split the adherence heatmap already uses for
    # student x val.
    _add_if_present(
        charts,
        df,
        ["strategy", "v_ok_numeric"],
        "Pass rate by prompt strategy",
        lambda: px.bar(
            df.groupby("strategy")["v_ok_numeric"].mean().reset_index(),
            x="strategy",
            y="v_ok_numeric",
            color="strategy",
            title="Pass rate by prompt strategy",
            labels={"v_ok_numeric": "Success probability"},
            template=TEMPLATE,
        ),
    )
    _add_if_present(
        charts,
        df,
        ["strategy", "coherence"],
        "Coherence stability by prompt strategy",
        lambda: px.box(
            df,
            x="strategy",
            y="coherence",
            color="strategy",
            title="Coherence stability by prompt strategy",
            template=TEMPLATE,
        ),
    )

    return charts


def build_high_dim_charts(df: pd.DataFrame) -> "list[tuple[str, str]]":
    """
    Sub-tab 2 -- High-Dim analytics (ported from ``get_high_dim_dashboard``).

    Parameters
    ----------
    df : pandas.DataFrame
        One run's responses, ``pandas.json_normalize``-flattened.

    Returns
    -------
    list[tuple[str, str]]
        ``(title, html)`` pairs, in display order. Empty if the required
        columns (``lexical_density``, ``ms_per_word``, ``cognitive_load``)
        aren't present.
    """
    required = ["lexical_density", "ms_per_word", "cognitive_load"]
    if not all(col in df.columns for col in required):
        return []

    df_plot = df.copy()
    if "archetype" in df_plot.columns:
        df_plot["archetype_id"] = df_plot["archetype"].astype("category").cat.codes

    fig0 = px.parallel_categories(
        df_plot,
        dimensions=["teacher", "student", "archetype", "v_ok_numeric"],
        color="archetype_id",
        # A plain hex list works as a continuous scale here (Plotly interpolates
        # between the listed stops) -- this app's own muted palette instead of
        # Plotly's bright default qualitative list, matching the surrounding chrome.
        color_continuous_scale=QUALITATIVE_PALETTE,
        title="Logic pipeline | Color: Archetype",
    )
    fig0.update_layout(coloraxis_showscale=False)

    fig1 = px.parallel_categories(
        df_plot,
        dimensions=["teacher", "student", "archetype", "v_ok_numeric"],
        color="v_ok_numeric",
        color_continuous_scale="RdYlGn",
        title="Logic pipeline | Color: v_ok (Success)",
    )

    fig2 = px.bar(
        df_plot,
        x="student",
        y="ms_per_word",
        color="v_ok_numeric",
        facet_col="teacher",
        barmode="group",
        title="Productivity by teacher | Inference efficiency",
        template="plotly_dark",
    )

    fig3 = px.scatter_matrix(
        df_plot,
        dimensions=["lexical_density", "ms_per_word", "cognitive_load"],
        color="teacher",
        title="Teacher impact matrix",
        template="plotly_dark",
    )

    fig4 = px.scatter_matrix(
        df_plot,
        dimensions=["lexical_density", "ms_per_word", "cognitive_load"],
        color="teacher",
        symbol="student",
        title="Cross-model dependency matrix",
        template="plotly_dark",
    )
    fig4.update_traces(diagonal_visible=False, marker=dict(size=4))

    return [
        ("Logic pipeline | Color: Archetype", figure_to_div(fig0)),
        ("Logic pipeline | Color: v_ok (Success)", figure_to_div(fig1)),
        ("Model productivity matrix", figure_to_div(fig2)),
        ("Teacher impact matrix", figure_to_div(fig3)),
        ("Cross-model dependency matrix", figure_to_div(fig4)),
    ]


def build_zipf_charts(df: pd.DataFrame) -> "list[tuple[str, str]]":
    """
    Sub-tab 3 -- Zipf deviation.

    Parameters
    ----------
    df : pandas.DataFrame
        One run's responses, ``pandas.json_normalize``-flattened.

    Returns
    -------
    list[tuple[str, str]]
        ``(title, html)`` pairs, in display order. Empty if
        ``zipf_deviation`` isn't present.
    """
    if "zipf_deviation" not in df.columns:
        return []

    charts = [
        (
            "Zipf deviation distribution (normalized)",
            figure_to_div(
                px.box(
                    df,
                    x="student",
                    y="zipf_deviation",
                    color="student",
                    title="Zipf deviation distribution (normalized)",
                    template=TEMPLATE,
                )
            ),
        )
    ]

    if "archetype" in df.columns:
        charts.append(
            (
                "Zipf deviation by archetype",
                figure_to_div(
                    px.bar(
                        df,
                        x="archetype",
                        y="zipf_deviation",
                        color="student",
                        barmode="group",
                        title="Zipf deviation by archetype",
                        template=TEMPLATE,
                    )
                ),
            )
        )

    return charts
