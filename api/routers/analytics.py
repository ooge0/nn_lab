"""
api.routers.analytics
========================

Stage 8 -- ``tab_analytics`` parity. Read-only, over the same persisted
responses :mod:`api.routers.runs` already summarizes -- three sub-tabs of
Plotly charts (Adherence & metrics / High-Dim analytics / Zipf deviation),
built by :mod:`web.plotting.analytics_charts`. No new metric computation:
every field charted here is already produced by
:meth:`core.services.experiment_runner.ExperimentRunner._run_one`.
"""

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from web.plotting.analytics_charts import build_adherence_charts, build_high_dim_charts, build_zipf_charts
from web.plotting.render import set_chart_theme

router = APIRouter(prefix="/analytics", tags=["analytics"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()


def _build_context(run_id: str) -> dict:
    """Load one run's responses and build all three sub-tabs' charts, or an empty-state context if the run has none."""
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}

    df = pd.json_normalize(responses)
    return {
        "selected_run_id": run_id,
        "has_data": True,
        "adherence_charts": build_adherence_charts(df),
        "high_dim_charts": build_high_dim_charts(df),
        "zipf_charts": build_zipf_charts(df),
    }


@router.get("", response_class=HTMLResponse)
def analytics_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's charts, if any runs exist."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_build_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "analytics.html", context)


@router.get("/charts", response_class=HTMLResponse)
def analytics_charts(request: Request, run_id: str) -> HTMLResponse:
    """
    Return the ``#analytics-charts`` fragment for one run -- used by the
    picker's htmx swap (``run_id`` as a query param, matching
    ``/runs/summary``'s pattern).

    Returns
    -------
    HTMLResponse
        200, with the rendered charts, if the run has persisted responses.
    HTMLResponse
        404, if the run has no persisted responses -- matches
        ``/runs/summary``'s convention for the same condition.
    """
    set_chart_theme(request.cookies.get("nn_lab_theme", "dark"))
    context = _build_context(run_id)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_analytics_charts.html", context, status_code=status_code)
