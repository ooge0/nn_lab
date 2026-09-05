"""
web.plotting.nlp_charts
==========================

Stage 9's three ``tab_nlp`` sub-tabs, ported from
``streamlit_app.py:1357-1541``. Unlike Stage 8's ``tab_analytics`` (which
builds its DataFrame with a plain ``pandas.json_normalize`` over raw
responses), the legacy ``tab_nlp`` builds it via
:meth:`core.analysis.data_contract.LabDataBridge.build_dataframe` -- a
genuine difference in what the two legacy tabs actually did, not an
inconsistency introduced here. Reusing the same bridge means every column
these charts reference is guaranteed present (:class:`~core.analysis
.data_contract.LabSchema` gives every declared field a default), unlike
Stage 8's charts, which needed to guard for columns real sparse data
sometimes lacks.
"""

import pandas as pd
import plotly.express as px

from web.plotting.render import figure_to_div

TEMPLATE = "plotly_white"


def build_nlp1_charts(df: pd.DataFrame) -> "list[tuple[str, str]]":
    """
    Sub-tab NLP-1 -- POS morphology, cognitive complexity, emotional engagement.

    Parameters
    ----------
    df : pandas.DataFrame
        Built via :meth:`core.analysis.data_contract.LabDataBridge.build_dataframe`.

    Returns
    -------
    list[tuple[str, str]]
        ``(title, html)`` pairs, in display order.
    """
    return [
        (
            "POS morphology profile",
            figure_to_div(
                px.scatter_ternary(
                    df,
                    a="pos_adj",
                    b="pos_noun",
                    c="pos_verb",
                    color="archetype",
                    size="word_count",
                    title="POS morphology profile",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Intelligence & vocabulary breadth",
            figure_to_div(
                px.scatter(
                    df,
                    x="readability_ari",
                    y="corrected_ttr",
                    color="archetype",
                    symbol="student",
                    size="word_count",
                    title="Cognitive complexity (readability vs. diversity)",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Bias & polarity analysis",
            figure_to_div(
                px.scatter(
                    df,
                    x="subjectivity",
                    y="sentiment",
                    color="archetype",
                    symbol="student",
                    size="lexical_density",
                    facet_col="bias",
                    size_max=15,
                    title="Emotional engagement (subjectivity vs. sentiment)",
                    template=TEMPLATE,
                )
            ),
        ),
    ]


def build_nlp2_charts(df: pd.DataFrame) -> "list[tuple[str, str]]":
    """
    Sub-tab NLP-2 -- emotional stability, repetition/fixation.

    Parameters
    ----------
    df : pandas.DataFrame
        Built via :meth:`core.analysis.data_contract.LabDataBridge.build_dataframe`.

    Returns
    -------
    list[tuple[str, str]]
        ``(title, html)`` pairs, in display order.
    """
    return [
        (
            "Emotional variability per archetype",
            figure_to_div(
                px.box(
                    df,
                    x="archetype",
                    y="sentiment_variance",
                    color="archetype",
                    points="all",
                    title="Emotional stability (sentiment variance)",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Repetition triggered by bias type",
            figure_to_div(
                px.box(
                    df,
                    x="bias",
                    y="repetition_score",
                    color="archetype",
                    points="all",
                    notched=True,
                    title="Repetition / fixation patterns",
                    template=TEMPLATE,
                )
            ),
        ),
    ]


def build_nlp3_charts(df: pd.DataFrame) -> "list[tuple[str, str]]":
    """
    Sub-tab NLP-3 -- sentence structure, neuropsychological metrics, coherence.

    Parameters
    ----------
    df : pandas.DataFrame
        Built via :meth:`core.analysis.data_contract.LabDataBridge.build_dataframe`.

    Returns
    -------
    list[tuple[str, str]]
        ``(title, html)`` pairs, in display order.
    """
    labels = {
        "neuro_self_focus": "Self-reference (I-Factor)",
        "rigidity": "Cognitive rigidity (Fixation)",
        "archetype": "Archetype cluster",
    }
    return [
        (
            "Sentence length per archetype",
            figure_to_div(
                px.box(
                    df,
                    x="archetype",
                    y="avg_sentence_length",
                    color="archetype",
                    points="all",
                    title="Syntactic flow (sentence length distribution)",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Egocentricity vs. fixation",
            figure_to_div(
                px.scatter(
                    df,
                    x="neuro_self_focus",
                    y="rigidity",
                    color="archetype",
                    size="word_count",
                    labels=labels,
                    hover_data=["bias", "student"],
                    title="Self-focus vs. cognitive rigidity",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Egocentricity vs. fixation by bias",
            figure_to_div(
                px.scatter(
                    df,
                    x="neuro_self_focus",
                    y="rigidity",
                    color="archetype",
                    facet_col="bias",
                    size="word_count",
                    hover_data=["student", "val"],
                    labels=labels,
                    title="Self-focus vs. cognitive rigidity (bias dependency)",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Linguistic rigidity: impact of bias",
            figure_to_div(
                px.box(
                    df,
                    x="bias",
                    y="rigidity",
                    color="archetype",
                    points="all",
                    notched=True,
                    hover_data=["student"],
                    title="Rigidity distribution by bias type",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Abstract thinking vs. processing load",
            figure_to_div(
                px.scatter(
                    df,
                    x="neuro_abstract_ratio_ext",
                    y="neuro_cognitive_load",
                    color="archetype",
                    size="word_count",
                    hover_data=["student"],
                    title="Abstraction vs. cognitive load",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Logical continuity per archetype",
            figure_to_div(
                px.box(
                    df,
                    x="archetype",
                    y="neuro_coherence",
                    color="archetype",
                    points="all",
                    hover_data=["student"],
                    title="Narrative coherence distribution",
                    template=TEMPLATE,
                )
            ),
        ),
        (
            "Emotional stability per archetype",
            figure_to_div(
                px.box(
                    df,
                    x="archetype",
                    y="sentiment_variance",
                    color="archetype",
                    points="all",
                    hover_data=["student"],
                    title="Emotional volatility (sentence variance)",
                    template=TEMPLATE,
                )
            ),
        ),
    ]
