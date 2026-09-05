"""
Unit tests for :mod:`core.services.cluster_discovery` -- Stage 10.

``compute_fit_indices`` is pure, deterministic math (scikit-learn metric
functions over already-fixed embeddings/labels, no randomness) and is
pinned exactly on a fixed synthetic dataset, per CLAUDE.md SS7. The
UMAP/HDBSCAN-driven functions (``run_plain_hdbscan``,
``run_behavioral_topology``) are *not* pinned to exact cluster-ID
assignments -- cluster label numbering is algorithm-internal and not
guaranteed stable across scikit-learn/hdbscan/umap-learn versions or
platforms even with a fixed ``random_state``, so pinning exact IDs would
make the suite fragile for the wrong reason. Instead they're tested
structurally: correct columns, correct shapes, correct filtering behavior,
outlier-subset correctness.
"""

import numpy as np
import pandas as pd
import pytest

from core.services.cluster_discovery import (
    ClusterDiscovery,
    compute_fit_indices,
    run_behavioral_topology,
    run_plain_hdbscan,
)

# --- compute_fit_indices: pinned, pure math -----------------------------


def test_compute_fit_indices_pinned_on_two_perfectly_separated_clusters():
    """
    Two tight, far-apart 2-point clusters -> silhouette should be very
    close to 1 (perfect separation), Davies-Bouldin very close to 0
    (tight, well-separated clusters), computed by scikit-learn directly so
    this pins *our wiring* of those functions, not their internal math.
    """
    embedding = np.array([[0.0, 0.0], [0.1, 0.1], [10.0, 10.0], [10.1, 10.1]])
    labels = np.array([0, 0, 1, 1])

    result = compute_fit_indices(embedding, labels)

    assert result["silhouette"] == pytest.approx(0.99, abs=1e-2)
    assert result["davies_bouldin"] == pytest.approx(0.01, abs=1e-3)
    assert result["ari"] == 0.0  # no archetypes passed
    assert result["noise_ratio"] == 0.0  # no -1 labels


def test_compute_fit_indices_single_cluster_uses_legacy_sentinels():
    """A single cluster (nothing to separate) can't compute silhouette/DBI -- matches the legacy app's own 0.0/99.0 sentinels, not a crash."""
    embedding = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    labels = np.array([0, 0, 0])

    result = compute_fit_indices(embedding, labels)

    assert result["silhouette"] == 0.0
    assert result["davies_bouldin"] == 99.0


def test_compute_fit_indices_ari_with_perfect_archetype_alignment():
    """ARI == 1.0 when cluster labels perfectly match the ground-truth archetype grouping."""
    embedding = np.array([[0.0, 0.0], [0.1, 0.1], [10.0, 10.0], [10.1, 10.1]])
    labels = np.array([0, 0, 1, 1])
    archetypes = pd.Series(["Detached", "Detached", "Anxious", "Anxious"])

    result = compute_fit_indices(embedding, labels, archetypes)

    assert result["ari"] == pytest.approx(1.0)


def test_compute_fit_indices_noise_ratio():
    """noise_ratio is the fraction of rows labeled -1 (HDBSCAN's noise sentinel)."""
    embedding = np.zeros((10, 2))
    labels = np.array([0, 0, 0, 0, 0, 0, 0, -1, -1, -1])

    result = compute_fit_indices(embedding, labels)

    assert result["noise_ratio"] == pytest.approx(0.3)


# --- run_plain_hdbscan: structural -----------------------------------------


def _synthetic_responses(n=40, seed=42):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "student": rng.choice(["qwen:latest", "phi3:latest"], n),
            "archetype": rng.choice(["Detached", "Anxious"], n),
            "output": ["a response with several words in it"] * n,
            "v_ok_numeric": 1,
            "coherence": rng.random(n),
            "sentiment": rng.standard_normal(n),
            "rigidity": rng.standard_normal(n),
            "word_count": rng.integers(10, 100, n),
        }
    )


def test_run_plain_hdbscan_adds_cluster_columns():
    """cluster_id and cluster_name columns get added, cluster_name derived correctly from cluster_id."""
    df = _synthetic_responses(n=40)

    result = run_plain_hdbscan(df, min_cluster_size=5, min_samples=1)

    assert "cluster_id" in result.columns
    assert "cluster_name" in result.columns
    assert len(result) == len(df)
    noise_rows = result[result["cluster_id"] == "-1"]
    assert (noise_rows["cluster_name"] == "Noise").all()
    non_noise = result[result["cluster_id"] != "-1"]
    if not non_noise.empty:
        assert non_noise["cluster_name"].str.startswith("Cluster ").all()


def test_run_plain_hdbscan_is_a_no_op_when_too_few_rows():
    """A dataset smaller than min_cluster_size is returned unchanged, not crashed on."""
    df = _synthetic_responses(n=3)

    result = run_plain_hdbscan(df, min_cluster_size=5, min_samples=1)

    assert "cluster_id" not in result.columns
    assert len(result) == 3


# --- run_behavioral_topology: structural ------------------------------------


def test_run_behavioral_topology_adds_expected_columns():
    """x_vis/y_vis/cluster_id/cluster_name all get added, one row per (filtered) input row."""
    df = _synthetic_responses(n=40)
    features = ["sentiment", "rigidity", "word_count", "coherence"]

    result = run_behavioral_topology(df, feature_cols=features, min_words=0, min_cluster_size=5, min_samples=1)

    for col in ("x_vis", "y_vis", "cluster_id", "cluster_name"):
        assert col in result.df.columns
    assert result.feature_cols == features
    assert len(result.df) <= len(df)


def test_run_behavioral_topology_filters_invalid_responses_when_requested():
    """filter_v_ok=True drops rows where v_ok_numeric == 0."""
    df = _synthetic_responses(n=40)
    df.loc[0:9, "v_ok_numeric"] = 0

    result = run_behavioral_topology(
        df,
        feature_cols=["sentiment", "rigidity"],
        filter_v_ok=True,
        min_words=0,
        min_cluster_size=5,
        min_samples=1,
    )

    assert (result.df["v_ok_numeric"] != 0).all()
    assert len(result.df) <= 30


def test_run_behavioral_topology_filters_short_outputs():
    """min_words drops rows whose output has fewer words than the threshold."""
    df = _synthetic_responses(n=40)
    df.loc[0:9, "output"] = "short"

    result = run_behavioral_topology(
        df,
        feature_cols=["sentiment", "rigidity"],
        min_words=3,
        min_cluster_size=5,
        min_samples=1,
    )

    assert "short" not in result.df["output"].values


def test_run_behavioral_topology_outliers_are_the_noise_labeled_subset():
    """outliers is exactly the cluster_id == -1 subset of df, nothing more or less."""
    df = _synthetic_responses(n=40)

    result = run_behavioral_topology(
        df, feature_cols=["sentiment", "rigidity"], min_words=0, min_cluster_size=5, min_samples=1
    )

    assert len(result.outliers) == (result.df["cluster_id"] == -1).sum()
    assert set(result.outliers.index).issubset(set(result.df.index))


def test_run_behavioral_topology_does_not_crash_when_filtering_removes_every_row():
    """
    Regression test for a real bug: filtering can legitimately leave zero
    rows (e.g. every response shorter than min_words), which crashed
    StandardScaler/UMAP with a 0-sample ValueError before this was
    guarded. Must return a usable (empty) result instead.
    """
    df = _synthetic_responses(n=10)
    df["output"] = "short"  # 1 word, below any realistic min_words

    result = run_behavioral_topology(
        df, feature_cols=["sentiment", "rigidity"], min_words=15, min_cluster_size=5, min_samples=1
    )

    assert len(result.df) == 0
    assert result.clusterer is None
    assert result.fit_indices == {}


def test_run_behavioral_topology_fit_indices_has_all_expected_keys():
    """fit_indices always has the four expected keys, values are floats."""
    df = _synthetic_responses(n=40)

    result = run_behavioral_topology(
        df, feature_cols=["sentiment", "rigidity"], min_words=0, min_cluster_size=5, min_samples=1
    )

    for key in ("silhouette", "davies_bouldin", "ari", "noise_ratio"):
        assert key in result.fit_indices
        assert isinstance(result.fit_indices[key], float)


# --- ClusterDiscovery (KMeans+PCA, existing pre-Stage-10 module): first tests ever written for it ---


def test_cluster_discovery_process_data_adds_expected_columns():
    """process_data adds cluster_id (str), x, y (PCA coords) -- no unit test existed for this pre-existing module before Stage 10."""
    df = _synthetic_responses(n=40)
    discovery = ClusterDiscovery(n_clusters=2)

    result = discovery.process_data(df.copy())

    assert "cluster_id" in result.columns
    assert "x" in result.columns
    assert "y" in result.columns
    assert result["cluster_id"].apply(lambda v: isinstance(v, str)).all()


def test_cluster_discovery_is_a_no_op_when_fewer_rows_than_n_clusters():
    """
    Regression test for a real bug: KMeans(n_clusters=3) raised
    ValueError('n_samples=2 should be >= n_clusters=3') instead of
    degrading gracefully like the empty-columns case -- caught by Stage
    10's own functional API test against a small synthetic run, not
    hypothetical. Must return df unmodified, matching the existing
    empty-columns contract.
    """
    df = _synthetic_responses(n=2)
    discovery = ClusterDiscovery(n_clusters=3)

    result = discovery.process_data(df.copy())

    assert "cluster_id" not in result.columns
    assert "x" not in result.columns
    assert len(result) == 2


def test_cluster_discovery_is_a_no_op_on_empty_numeric_data():
    """A DataFrame with no numeric columns at all is returned unchanged, not crashed on."""
    df = pd.DataFrame({"student": ["a", "b"], "archetype": ["x", "y"]})
    discovery = ClusterDiscovery(n_clusters=2)

    result = discovery.process_data(df.copy())

    assert "cluster_id" not in result.columns


def test_cluster_discovery_component_dependencies_available_after_process_data():
    """get_component_dependencies returns PC1/PC2 loadings after process_data has fit the PCA, keyed by feature name."""
    df = _synthetic_responses(n=40)
    discovery = ClusterDiscovery(n_clusters=2)
    discovery.process_data(df.copy())

    pc1, pc2 = discovery.get_component_dependencies()

    assert pc1 is not None and pc2 is not None
    assert set(pc1.index) == set(discovery.feature_names)


def test_cluster_discovery_component_dependencies_none_before_fit():
    """Before process_data ever runs, get_component_dependencies returns (None, None) rather than raising."""
    discovery = ClusterDiscovery(n_clusters=2)

    pc1, pc2 = discovery.get_component_dependencies()

    assert pc1 is None and pc2 is None
