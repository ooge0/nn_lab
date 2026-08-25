"""
web.plotting.cluster_charts
==============================

Stage 10 presentation: KMeans+PCA (``streamlit_app.py``'s "K-Means (PCA)"
sub-tab), plain density clustering ("HDBSCAN (Density)"), and the
"Behavioral topology" UMAP+HDBSCAN+confirmatory-fit-indices workflow's 7
sub-views. See :mod:`core.services.cluster_discovery` for why only these
three are ported (the legacy tab has two further, confirmed-duplicate
UMAP+HDBSCAN implementations, deliberately not carried forward) and for
all the actual computation -- everything here is presentation only.

One deliberate simplification from the legacy "Research mode" sub-tab:
its X/Y feature-pair scatter used two live dropdowns letting the viewer
pick any pair interactively. This stage fixes the pair to the first two
active feature columns instead of building a second interactive
control -- the legacy control is a UX nicety over already-plotted data,
not new analysis; a real interactive picker can be added later if wanted.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px

from core.services.cluster_discovery import BehavioralTopologyResult
from web.plotting.mpl_render import figure_to_img_tag
from web.plotting.render import figure_to_div

TEMPLATE = "plotly_white"


def _styled_table_html(df: pd.DataFrame, cmap: str, fmt: str = "{:.1f}%") -> str:
    """Render a DataFrame as a gradient-styled HTML table, matching the legacy `.style.background_gradient()` look."""
    if df.empty:
        return "<p>No data.</p>"
    return df.style.background_gradient(cmap=cmap).format(fmt).to_html()


def build_kmeans_pca_view(df: pd.DataFrame, cluster_discovery, color_by: str = "archetype") -> dict:
    """
    "K-Means (PCA)" sub-tab.

    Parameters
    ----------
    df : pandas.DataFrame
        A run's responses, already processed by ``cluster_discovery.process_data``
        (must have ``x``/``y``/``cluster_id`` columns).
    cluster_discovery : core.analysis.cluster_discovery.ClusterDiscovery
        The already-fit instance (for ``get_component_dependencies``).
    color_by : str, optional
        Which column to color the scatter by -- ``archetype``, ``cluster_id``,
        ``student``, or ``v_ok``.

    Returns
    -------
    dict
        ``scatter``, ``pc1_drivers``, ``pc2_drivers`` (chart HTML), and
        ``purity_table`` (styled HTML table, or ``None`` if ``archetype``
        isn't present).
    """
    fig = px.scatter(
        df,
        x="x",
        y="y",
        color=color_by if color_by in df.columns else "cluster_id",
        symbol="student",
        hover_data=[c for c in ["archetype", "bias", "val", "v_ok"] if c in df.columns],
        title=f"PCA space: {color_by.capitalize()} distribution",
        template=TEMPLATE,
        color_discrete_sequence=px.colors.qualitative.Vivid,
    )
    fig.update_traces(marker=dict(size=9, opacity=0.75, line=dict(width=1, color="rgba(255,255,255,0.5)")))
    fig.update_layout(height=600, legend_title_text="Legend")

    pc1, pc2 = cluster_discovery.get_component_dependencies()

    def _driver_chart(drivers, axis_name):
        if drivers is None:
            return None
        top = drivers.reindex(drivers.abs().sort_values(ascending=False).index).head(10)
        fig_dr = px.bar(
            top,
            orientation="h",
            labels={"value": "Impact strength", "index": "NLP metric"},
            color=top.values,
            color_continuous_scale="RdBu",
            title=f"Top drivers for {axis_name}",
        )
        fig_dr.update_layout(showlegend=False, height=350, margin=dict(l=20, r=20, t=40, b=20))
        return figure_to_div(fig_dr)

    purity_table = None
    if "archetype" in df.columns:
        purity = pd.crosstab(df["cluster_id"], df["archetype"], normalize="index") * 100
        purity_table = _styled_table_html(purity, "YlGnBu")

    return {
        "scatter": figure_to_div(fig),
        "pc1_drivers": _driver_chart(pc1, "X-Axis (PC1)"),
        "pc2_drivers": _driver_chart(pc2, "Y-Axis (PC2)"),
        "purity_table": purity_table,
    }


def build_plain_hdbscan_view(df_with_pca_xy: pd.DataFrame, hdb_df: pd.DataFrame) -> dict:
    """
    "HDBSCAN (Density)" sub-tab -- density clustering on full-dimensional
    features (:func:`core.services.cluster_discovery.run_plain_hdbscan`),
    visualized using the PCA x/y coordinates from the K-Means view for
    consistency (matching the legacy app's own approach).

    Parameters
    ----------
    df_with_pca_xy : pandas.DataFrame
        The K-Means view's already-processed DataFrame (has ``x``/``y``).
    hdb_df : pandas.DataFrame
        Output of ``run_plain_hdbscan`` (has ``cluster_id``/``cluster_name``).

    Returns
    -------
    dict
        ``scatter`` (chart HTML), ``noise_count``, ``total``.
    """
    plot_df = df_with_pca_xy.copy()
    plot_df["cluster_name"] = hdb_df["cluster_name"].values
    fig = px.scatter(
        plot_df,
        x="x",
        y="y",
        color="cluster_name",
        symbol="student" if "student" in plot_df.columns else None,
        title="HDBSCAN: density-based groups",
        hover_data=[c for c in ["archetype", "bias"] if c in plot_df.columns],
        color_discrete_map={"Noise": "#7f8c8d"},
        template=TEMPLATE,
    )
    noise_count = int((hdb_df["cluster_name"] == "Noise").sum())
    return {"scatter": figure_to_div(fig), "noise_count": noise_count, "total": len(hdb_df)}


def build_behavioral_topology_views(result: "BehavioralTopologyResult") -> dict:
    """
    "Behavioral topology"'s 7 sub-views, all from one already-computed
    :class:`~core.services.cluster_discovery.BehavioralTopologyResult`.

    Returns
    -------
    dict
        ``projection`` (chart HTML + 4 summary numbers), ``topology``
        (scatter + MST + condensed-tree, all chart HTML), ``membership``
        (3 styled tables), ``research`` (correlation heatmap + one
        feature-pair scatter), ``anomalies`` (outlier chart + table HTML),
        ``fit_indices`` (the raw dict from ``compute_fit_indices``).
    """
    df = result.df

    # --- Latent projection ---
    fig_proj = px.scatter(
        df,
        x="x_vis",
        y="y_vis",
        color="cluster_name",
        symbol="student" if "student" in df.columns else None,
        hover_data=[
            c for c in ["archetype", "bias", "val", "v_ok_numeric", "word_count", "coherence"] if c in df.columns
        ],
        template=TEMPLATE,
        title="UMAP projection space",
    )
    fig_proj.update_traces(marker=dict(size=8, opacity=0.75))
    n_clusters = len({lbl for lbl in df["cluster_id"] if lbl != -1})
    projection = {
        "chart": figure_to_div(fig_proj),
        "samples": len(df),
        "clusters": n_clusters,
        "outlier_pct": round(len(result.outliers) / len(df) * 100, 1) if len(df) else 0.0,
        "features": len(result.feature_cols),
    }

    # --- HDBSCAN topology: scatter + MST + condensed tree ---
    fig_topo = px.scatter(
        df,
        x="x_vis",
        y="y_vis",
        color="cluster_name",
        symbol="student" if "student" in df.columns else None,
        hover_data=[c for c in ["archetype", "bias", "step", "output"] if c in df.columns],
        template=TEMPLATE,
        title="Behavioral topology scatter map",
    )
    fig_topo.update_traces(marker=dict(size=9, opacity=0.75, line=dict(width=1, color="rgba(255,255,255,0.5)")))

    # hdbscan's own MST/condensed-tree .plot() calls can raise on certain cluster
    # geometries (a real, reproducible matplotlib transform error hit during this
    # stage's own smoke test, not a hypothetical) -- the legacy app already wraps
    # both in a bare try/except for exactly this reason; matched here rather than
    # dropped, so a plot failure degrades gracefully instead of 500ing the page.
    mst_html = None
    if hasattr(result.clusterer, "minimum_spanning_tree_") and result.clusterer.minimum_spanning_tree_ is not None:
        try:
            fig_mst, ax_mst = _dark_mpl_axes()
            result.clusterer.minimum_spanning_tree_.plot(
                axis=ax_mst,
                node_size=0,
                edge_alpha=0.5,
                edge_cmap="viridis",
                edge_linewidth=1.5,
                vary_line_width=True,
            )
            ax_mst.axis("off")
            mst_html = figure_to_img_tag(fig_mst, alt="Minimum spanning tree")
        except Exception:
            mst_html = None

    condensed_html = None
    if hasattr(result.clusterer, "condensed_tree_") and result.clusterer.condensed_tree_ is not None:
        try:
            fig_cond, ax_cond = _dark_mpl_axes()
            result.clusterer.condensed_tree_.plot(select_clusters=True, axis=ax_cond)
            condensed_html = figure_to_img_tag(fig_cond, alt="Condensed tree")
        except Exception:
            condensed_html = None

    topology = {"scatter": figure_to_div(fig_topo), "mst": mst_html, "condensed_tree": condensed_html}

    # --- Cluster membership ---
    membership = {}
    if "archetype" in df.columns:
        membership["archetype_table"] = _styled_table_html(
            pd.crosstab(df["cluster_name"], df["archetype"], normalize="index") * 100,
            "YlGnBu",
        )
    if "student" in df.columns:
        membership["model_table"] = _styled_table_html(
            pd.crosstab(df["cluster_name"], df["student"], normalize="index") * 100,
            "Blues",
        )
    if result.feature_cols:
        centroids = df.groupby("cluster_name")[result.feature_cols].mean()
        membership["centroid_table"] = _styled_table_html(centroids, "RdBu_r", fmt="{:.3f}")

    # --- Research mode ---
    research = {}
    if result.feature_cols:
        corr = df[result.feature_cols].corr(numeric_only=True)
        fig_corr = px.imshow(
            corr, template=TEMPLATE, color_continuous_scale="RdBu_r", title="Feature correlation matrix"
        )
        research["correlation_heatmap"] = figure_to_div(fig_corr)
    if len(result.feature_cols) >= 2:
        x_feat, y_feat = result.feature_cols[0], result.feature_cols[1]
        fig_feat = px.scatter(
            df,
            x=x_feat,
            y=y_feat,
            color="cluster_name",
            symbol="student" if "student" in df.columns else None,
            template=TEMPLATE,
            title=f"{x_feat} vs. {y_feat} by cluster",
        )
        research["feature_scatter"] = figure_to_div(fig_feat)
        research["x_feature"], research["y_feature"] = x_feat, y_feat

    # --- Anomalies ---
    anomalies: dict = {"outlier_pct": round(len(result.outliers) / len(df) * 100, 1) if len(df) else 0.0}
    if not result.outliers.empty and "student" in result.outliers.columns:
        fig_out = px.bar(result.outliers["student"].value_counts(), title="Outliers by model", template=TEMPLATE)
        anomalies["by_model_chart"] = figure_to_div(fig_out)
        display_cols = [
            c
            for c in ["student", "archetype", "bias", "output", "cluster_name", "coherence", "rigidity", "sentiment"]
            if c in result.outliers.columns
        ]
        anomalies["table_html"] = result.outliers[display_cols].to_html(index=False, escape=True)
    else:
        anomalies["table_html"] = None

    return {
        "projection": projection,
        "topology": topology,
        "membership": membership,
        "research": research,
        "anomalies": anomalies,
        "fit_indices": result.fit_indices,
    }


def _dark_mpl_axes():
    """A matplotlib Figure/Axes pair styled to match the legacy app's dark MST/condensed-tree background."""
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    return fig, ax
