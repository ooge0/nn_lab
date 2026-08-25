"""
api.routers.clusters
=======================

Stage 10 -- ``tab_clusters`` parity (partial scope, decided with the
author after finding real duplication in the legacy code -- see
:mod:`core.services.cluster_discovery`'s module docstring): K-Means+PCA,
plain density HDBSCAN, and the "Behavioral topology"
UMAP+HDBSCAN+confirmatory-fit-indices workflow. The legacy tab's other two
UMAP+HDBSCAN implementations are confirmed-duplicate scope creep, not
ported.

Computation parameters (cluster counts, HDBSCAN min-size, UMAP neighbors,
etc.) use the legacy UI's own default values rather than exposing the full
multi-expander configuration surface -- the deliverable is making the
existing numbers/plots reachable, not rebuilding every interactive slider.
"""

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.services.cluster_discovery import ClusterDiscovery, run_behavioral_topology, run_plain_hdbscan
from web.plotting.cluster_charts import build_behavioral_topology_views, build_kmeans_pca_view, build_plain_hdbscan_view
from web.plotting.mpl_render import set_chart_theme as set_mpl_chart_theme
from web.plotting.render import set_chart_theme as set_plotly_chart_theme

router = APIRouter(prefix="/clusters", tags=["clusters"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()

# Matches the legacy "Behavioral" + "Linguistic" default feature-group selection.
_DEFAULT_FEATURES = [
    "sentiment",
    "subjectivity",
    "rigidity",
    "modality",
    "cognitive_density",
    "cognitive_load",
    "coherence",
    "abstract_ratio",
    "semantic_overlap",
    "lexical_density",
    "corrected_ttr",
    "avg_sentence_length",
    "word_count",
    "readability_ari",
    "unique_ratio",
    "repetition_score",
    "punc_density",
    "zipf_deviation",
]


def _build_context(run_id: str) -> dict:
    """Load one run's responses and build all three sub-tabs' views, or an empty-state context if the run has none."""
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}

    df = pd.json_normalize(responses)

    discovery = ClusterDiscovery(n_clusters=3)
    df_pca = discovery.process_data(df.copy())
    kmeans = None
    if "x" in df_pca.columns:  # process_data returns df unmodified if there are fewer rows than n_clusters
        kmeans = build_kmeans_pca_view(df_pca, discovery, color_by="archetype")

    hdb_df = run_plain_hdbscan(df.copy(), min_cluster_size=5, min_samples=1)
    plain_hdbscan = None
    if "cluster_id" in hdb_df.columns and "x" in df_pca.columns:
        plain_hdbscan = build_plain_hdbscan_view(df_pca, hdb_df)

    behavioral_topology = None
    active_features = [c for c in _DEFAULT_FEATURES if c in df.columns]
    if active_features:
        bt_result = run_behavioral_topology(df, feature_cols=active_features, min_cluster_size=10, min_samples=3)
        if (
            "x_vis" in bt_result.df.columns
        ):  # absent if filtering/row-count guards inside run_behavioral_topology short-circuited
            behavioral_topology = build_behavioral_topology_views(bt_result)

    return {
        "selected_run_id": run_id,
        "has_data": True,
        "kmeans": kmeans,
        "plain_hdbscan": plain_hdbscan,
        "behavioral_topology": behavioral_topology,
    }


@router.get("", response_class=HTMLResponse)
def clusters_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's clustering views, if any runs exist."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_build_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "clusters.html", context)


@router.get("/charts", response_class=HTMLResponse)
def clusters_charts(request: Request, run_id: str) -> HTMLResponse:
    """
    Return the ``#clusters-charts`` fragment for one run -- used by the
    picker's htmx swap (``run_id`` as a query param, matching
    ``/analytics/charts``'s pattern).

    Returns
    -------
    HTMLResponse
        200, with the rendered views, if the run has persisted responses.
    HTMLResponse
        404, if the run has no persisted responses.
    """
    theme = request.cookies.get("nn_lab_theme", "dark")
    set_plotly_chart_theme(theme)
    set_mpl_chart_theme(theme)
    context = _build_context(run_id)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_clusters_charts.html", context, status_code=status_code)
