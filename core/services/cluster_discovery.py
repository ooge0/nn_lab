"""
core.services.cluster_discovery
==================================

Stage 10's clustering/dimensionality-reduction computation, ported from
``streamlit_app.py``'s ``tab_clusters`` (1548-2855). Business logic only --
no Plotly/matplotlib here, matching the split the refactor plan calls for
(:mod:`web.plotting.cluster_charts` owns presentation).

Scope, decided with the author after finding real duplication in the
legacy code: the legacy tab has *three* overlapping implementations of the
same UMAP+HDBSCAN+confirmatory-fit-indices workflow ("HDBSCAN + UMAP",
"HDBSCAN + UMAP v.2", and inside "Behavioral topology"'s own sub-tabs) --
confirmed by counting calls, not just skimming: ``UMAP()`` invoked 4 times,
``HDBSCAN()`` 4 times, each of the three fit-index functions 3 times, all
within one 1307-line tab. Only "Behavioral topology" (the most complete,
most recently-iterated version -- feature-group selection, real data
filtering, 7 organized sub-views) is ported; "HDBSCAN + UMAP" and its
"v.2" are confirmed-duplicate scope creep, deliberately not carried
forward -- matching how ``data_contract_old.py`` was handled earlier in
this migration.

One real bug found while reading the legacy code and *not* ported forward:
"Behavioral topology"'s own "HDBSCAN topology > Scatter map" sub-view read
``df_clustered``/``hdb_labels`` -- module-level variables left over from
the earlier ``sub_tab_hdbscan_UMAP`` block (Streamlit's flat top-to-bottom
script scope lets this "work" by accident), not this tab's own freshly
computed data. Since that earlier block isn't ported at all, this bug has
nothing to leak from here -- every view below uses only this module's own
computed DataFrame.
"""

from typing import Optional

import numpy as np
import pandas as pd
import hdbscan
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from umap import UMAP

from core.analysis.cluster_discovery import ClusterDiscovery

__all__ = [
    "ClusterDiscovery",
    "run_plain_hdbscan",
    "BehavioralTopologyResult",
    "run_behavioral_topology",
    "compute_fit_indices",
]


def run_plain_hdbscan(df: pd.DataFrame, min_cluster_size: int = 5, min_samples: int = 1) -> pd.DataFrame:
    """
    Density clustering directly on full-dimensional scaled features (no
    UMAP) -- ``streamlit_app.py``'s standalone "HDBSCAN (Density)" sub-tab.
    Genuinely distinct from the UMAP-based workflow below: it clusters on
    the full feature space, not a low-dimensional embedding.

    Parameters
    ----------
    df : pandas.DataFrame
        One run's responses, numeric metric columns present.
    min_cluster_size : int, optional
        HDBSCAN's ``min_cluster_size``.
    min_samples : int, optional
        HDBSCAN's ``min_samples``.

    Returns
    -------
    pandas.DataFrame
        Copy of ``df`` with ``cluster_id`` (str) and ``cluster_name``
        (``"Noise"`` or ``"Cluster N"``) columns added. Unchanged if there
        are fewer numeric rows than ``min_cluster_size``.
    """
    numeric = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all").fillna(0)
    if numeric.shape[0] <= min_cluster_size:
        return df

    scaled = StandardScaler().fit_transform(numeric)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, gen_min_span_tree=True)
    labels = clusterer.fit_predict(scaled)

    result = df.copy()
    result["cluster_id"] = labels.astype(str)
    result["cluster_name"] = [("Noise" if lbl == -1 else f"Cluster {lbl}") for lbl in labels]
    return result


def compute_fit_indices(embedding: np.ndarray, labels: np.ndarray, archetypes: "Optional[pd.Series]" = None) -> dict:
    """
    CLAUDE.md SS3b's corpus-level confirmatory-validation numbers --
    construct-validity proxies, not a pass/fail judgment (that stays the
    author's to interpret).

    Parameters
    ----------
    embedding : numpy.ndarray
        The (already-fit) coordinates clustering was performed on.
    labels : numpy.ndarray
        Cluster labels for each row (``-1`` = noise/outlier).
    archetypes : pandas.Series, optional
        Ground-truth archetype label per row, for ARI. ``0.0`` if omitted.

    Returns
    -------
    dict
        ``silhouette`` (higher is better, undefined/``0.0`` for a single
        cluster), ``davies_bouldin`` (lower is better, ``99.0`` sentinel
        for a single cluster -- matches the legacy app's own sentinel),
        ``ari`` (label-alignment vs. ``archetypes``), ``noise_ratio``
        (fraction of rows labeled ``-1``).
    """
    distinct = len(set(labels))
    if distinct > 1:
        silhouette = float(silhouette_score(embedding, labels))
        davies_bouldin = float(davies_bouldin_score(embedding, labels))
    else:
        silhouette = 0.0
        davies_bouldin = 99.0

    ari = float(adjusted_rand_score(archetypes, labels)) if archetypes is not None else 0.0
    noise_ratio = float((labels == -1).sum() / len(labels)) if len(labels) else 0.0

    return {"silhouette": silhouette, "davies_bouldin": davies_bouldin, "ari": ari, "noise_ratio": noise_ratio}


class BehavioralTopologyResult:
    """
    Everything "Behavioral topology"'s 7 sub-views need, computed once.

    Attributes
    ----------
    df : pandas.DataFrame
        Filtered input, with ``x_vis``/``y_vis`` (2D UMAP projection, for
        plotting), ``cluster_id``/``cluster_name`` (from HDBSCAN on a
        *separate*, higher-dimensional UMAP embedding -- matching the
        legacy app's deliberate two-embedding split: a low-dimensional
        space for visualization, a different one for the actual density
        clustering, since forcing both onto the same 2D projection distorts
        density) added.
    feature_cols : list of str
        The numeric feature columns actually used.
    outliers : pandas.DataFrame
        Subset of ``df`` where ``cluster_id == -1``.
    fit_indices : dict
        See :func:`compute_fit_indices`.
    clusterer : hdbscan.HDBSCAN
        The fit clusterer -- exposes ``minimum_spanning_tree_``/
        ``condensed_tree_`` for topology plots.
    """

    def __init__(self, df, feature_cols, outliers, fit_indices, clusterer):
        self.df = df
        self.feature_cols = feature_cols
        self.outliers = outliers
        self.fit_indices = fit_indices
        self.clusterer = clusterer


def run_behavioral_topology(
    df: pd.DataFrame,
    feature_cols: "list[str]",
    *,
    filter_v_ok: bool = True,
    min_words: int = 15,
    remove_json: bool = True,
    min_coherence: float = -1.0,
    remove_duplicates: bool = False,
    vis_neighbors: int = 15,
    vis_min_dist: float = 0.1,
    cluster_neighbors: int = 20,
    cluster_components: int = 15,
    min_cluster_size: int = 10,
    min_samples: int = 3,
) -> BehavioralTopologyResult:
    """
    The "Behavioral topology" workflow: filter -> two UMAP embeddings
    (2D for visualization, N-D for clustering) -> HDBSCAN on the N-D one
    -> fit indices. Parameter names and defaults match the legacy sliders
    exactly.

    Parameters
    ----------
    df : pandas.DataFrame
        One run's responses.
    feature_cols : list of str
        Numeric metric columns to cluster on (the legacy app's
        feature-group multiselect, e.g. "Behavioral"/"Linguistic"/
        "Runtime"/"Validation" groups -- callers choose which are active).
    filter_v_ok : bool, optional
        Drop rows where ``v_ok_numeric == 0``.
    min_words : int, optional
        Drop rows whose ``output`` has fewer words.
    remove_json : bool, optional
        Drop rows whose ``output`` looks like raw un-parsed JSON.
    min_coherence : float, optional
        Drop rows below this ``coherence`` value.
    remove_duplicates : bool, optional
        Drop rows with a duplicate ``output``.
    vis_neighbors, vis_min_dist : optional
        UMAP params for the 2D visualization embedding.
    cluster_neighbors, cluster_components : optional
        UMAP params for the higher-dimensional clustering embedding.
    min_cluster_size, min_samples : optional
        HDBSCAN params.

    Returns
    -------
    BehavioralTopologyResult
    """
    work = df.copy()

    if filter_v_ok and "v_ok_numeric" in work.columns:
        work = work[work["v_ok_numeric"] != 0]
    if "output" in work.columns:
        # pandas-stubs doesn't model .str.len() on a Series of lists (only on string dtype), even
        # though pandas itself supports it at runtime (returns each list's length) -- a stub gap,
        # not a real type error.
        work = work[work["output"].astype(str).str.split().str.len() >= min_words]  # type: ignore[misc]
        if remove_json:
            work = work[~work["output"].astype(str).str.contains(r'^\{"text":', regex=True, na=False)]
    if "coherence" in work.columns:
        work = work[work["coherence"] >= min_coherence]
    if remove_duplicates and "output" in work.columns:
        work = work.drop_duplicates(subset=["output"])

    # Filtering can legitimately remove everything (e.g. every response shorter
    # than min_words), and UMAP itself crashes (not gracefully) when there are
    # too few rows relative to n_neighbors -- "zero-size array to reduction
    # operation maximum which has no identity". Both caught by this stage's
    # own functional tests against small synthetic runs, not hypothetical.
    # Mirrors run_plain_hdbscan's own "not enough data" threshold convention.
    min_rows_needed = max(min_cluster_size, vis_neighbors, cluster_neighbors) + 1
    if len(work) < min_rows_needed:
        return BehavioralTopologyResult(df=work, feature_cols=[], outliers=work, fit_indices={}, clusterer=None)

    active_features = [c for c in feature_cols if c in work.columns]
    numeric = work[active_features].copy().replace([np.inf, -np.inf], np.nan).fillna(0)

    for col in ("cluster_id", "cluster_name"):
        if col in work.columns:
            # pandas-stubs' Series.apply overload doesn't include every numpy scalar type this
            # lambda can legitimately return (complex/bytes/memoryview) -- real at runtime for the
            # cluster_id/cluster_name values this actually sees, a stub gap, not a real type error.
            work[col] = work[col].apply(lambda x: x if np.isscalar(x) else str(x))  # type: ignore[arg-type,return-value]

    scaled = StandardScaler().fit_transform(numeric)

    vis_embedding = UMAP(
        n_neighbors=vis_neighbors, min_dist=vis_min_dist, n_components=2, random_state=42
    ).fit_transform(scaled)
    work["x_vis"] = vis_embedding[:, 0]
    work["y_vis"] = vis_embedding[:, 1]

    cluster_embedding = UMAP(
        n_neighbors=cluster_neighbors,
        min_dist=0.0,
        n_components=cluster_components,
        random_state=42,
    ).fit_transform(scaled)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        prediction_data=True,
        gen_min_span_tree=True,
    )
    labels = clusterer.fit_predict(cluster_embedding)

    work["cluster_id"] = labels
    work["cluster_name"] = [("Noise" if lbl == -1 else f"Cluster {lbl}") for lbl in labels]
    outliers = work[work["cluster_id"] == -1].copy()

    fit_indices = compute_fit_indices(
        cluster_embedding,
        labels,
        work["archetype"] if "archetype" in work.columns else None,
    )

    return BehavioralTopologyResult(
        df=work,
        feature_cols=active_features,
        outliers=outliers,
        fit_indices=fit_indices,
        clusterer=clusterer,
    )
