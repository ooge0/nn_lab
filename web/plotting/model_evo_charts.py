"""
web.plotting.model_evo_charts
================================

Stage 11 presentation -- ``streamlit_app.py``'s "LLM evaluation" tab
(:class:`~core.analysis.model_evaluation.ModelEvaluation`, a pre-existing,
framework-agnostic logistic-regression baseline). No new computation here;
this module only turns :meth:`~core.analysis.model_evaluation
.ModelEvaluation.evaluate`'s result dict into HTML/Plotly fragments,
matching the legacy tab's confusion-matrix heatmap and feature-importance
bar chart exactly (``px.imshow``/``px.bar``).
"""

import pandas as pd
import plotly.express as px

from web.plotting.render import figure_to_div

TEMPLATE = "plotly_white"


def build_model_evo_view(results: dict) -> dict:
    """
    Render one :meth:`~core.analysis.model_evaluation.ModelEvaluation.evaluate`
    result as HTML/Plotly fragments.

    Parameters
    ----------
    results : dict
        The dict returned by ``ModelEvaluation.evaluate()`` -- keys
        ``precision``/``recall``/``f1_score``/``roc_auc``,
        ``confusion_matrix`` (list of lists), ``classification_report``
        (str), ``top_features`` (list of ``{feature, weight, abs_weight}``
        records).

    Returns
    -------
    dict
        ``precision``/``recall``/``f1_score``/``roc_auc`` (passed through),
        ``confusion_matrix_table`` (HTML), ``confusion_matrix_chart``
        (Plotly div), ``classification_report`` (passed through, rendered
        in a ``<pre>``), ``top_features_table`` (HTML),
        ``top_features_chart`` (Plotly div, or ``None`` if no features).
    """
    cm = results["confusion_matrix"]
    n_classes = len(cm)
    cm_df = pd.DataFrame(
        cm,
        columns=[f"Pred {i}" for i in range(n_classes)],
        index=[f"True {i}" for i in range(n_classes)],
    )
    cm_fig = px.imshow(cm, text_auto=True, title="Confusion matrix heatmap", template=TEMPLATE)

    feature_df = pd.DataFrame(results["top_features"])
    top_features_chart = None
    if not feature_df.empty:
        fig = px.bar(feature_df.head(10), x="feature", y="abs_weight", title="Feature importance", template=TEMPLATE)
        top_features_chart = figure_to_div(fig)

    return {
        "precision": results["precision"],
        "recall": results["recall"],
        "f1_score": results["f1_score"],
        "roc_auc": results["roc_auc"],
        "confusion_matrix_table": cm_df.to_html(),
        "confusion_matrix_chart": figure_to_div(cm_fig),
        "classification_report": results["classification_report"],
        "top_features_table": feature_df.to_html(index=False) if not feature_df.empty else None,
        "top_features_chart": top_features_chart,
    }
