"""
api.routers.nlp
==================

Stage 9 -- ``tab_nlp`` parity. Read-only, over the same persisted responses
:mod:`api.routers.runs`/:mod:`api.routers.analytics` already read -- three
sub-tabs of Plotly charts (POS/cognitive/emotional, emotional
stability/repetition, sentence structure/neuro/coherence), built by
:mod:`web.plotting.nlp_charts` over a DataFrame from
:class:`core.analysis.data_contract.LabDataBridge`. No new metric
computation.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.analysis.data_contract import LabDataBridge
from web.plotting.nlp_charts import build_nlp1_charts, build_nlp2_charts, build_nlp3_charts
from web.plotting.render import set_chart_theme

router = APIRouter(prefix="/nlp", tags=["nlp"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()


def _build_context(run_id: str) -> dict:
    """Load one run's responses and build all three sub-tabs' charts, or an empty-state context if the run has none."""
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}

    df = LabDataBridge.build_dataframe(responses)
    return {
        "selected_run_id": run_id,
        "has_data": True,
        "nlp1_charts": build_nlp1_charts(df),
        "nlp2_charts": build_nlp2_charts(df),
        "nlp3_charts": build_nlp3_charts(df),
    }


@router.get("", response_class=HTMLResponse)
def nlp_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's charts, if any runs exist."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_build_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "nlp.html", context)


@router.get("/charts", response_class=HTMLResponse)
def nlp_charts(request: Request, run_id: str) -> HTMLResponse:
    """
    Return the ``#nlp-charts`` fragment for one run -- used by the picker's
    htmx swap (``run_id`` as a query param, matching
    ``/analytics/charts``'s pattern).

    Returns
    -------
    HTMLResponse
        200, with the rendered charts, if the run has persisted responses.
    HTMLResponse
        404, if the run has no persisted responses.
    """
    set_chart_theme(request.cookies.get("nn_lab_theme", "dark"))
    context = _build_context(run_id)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_nlp_charts.html", context, status_code=status_code)
