"""
api.routers.benchmark
========================

Stage 12 -- ``tab_benchmark`` parity: read-only aggregation over one run's
already-persisted responses (dataset overview, pass-rate/latency/quality
charts, weighted model leaderboard). Same read-only-over-accumulated-data
pattern as Stage 7's ``/runs`` and Stage 8's ``/analytics``.
"""

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from web.plotting.benchmark_charts import build_benchmark_view
from web.plotting.render import set_chart_theme

router = APIRouter(prefix="/benchmark", tags=["benchmark"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()


def _build_context(run_id: str) -> dict:
    """Load one run's responses and build the benchmark report, or an empty-state context if the run has none or lacks the required columns."""
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}

    df = pd.json_normalize(responses)
    view = build_benchmark_view(df)
    if view is None:
        return {"selected_run_id": run_id, "has_data": True, "insufficient_columns": True}
    return {"selected_run_id": run_id, "has_data": True, "insufficient_columns": False, **view}


@router.get("", response_class=HTMLResponse)
def benchmark_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's benchmark report, if any runs exist."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_build_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "benchmark.html", context)


@router.get("/report", response_class=HTMLResponse)
def benchmark_report(request: Request, run_id: str) -> HTMLResponse:
    """
    Return the ``#benchmark-report`` fragment for one run -- used by the
    picker's htmx swap.

    Returns
    -------
    HTMLResponse
        200, with the rendered report, if the run has persisted responses.
    HTMLResponse
        404, if the run has no persisted responses.
    """
    set_chart_theme(request.cookies.get("nn_lab_theme", "dark"))
    context = _build_context(run_id)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_benchmark_report.html", context, status_code=status_code)
