"""
api.routers.model_evo
========================

Stage 11 -- ``tab_model_evo`` parity: fits a baseline logistic-regression
model (:class:`~core.analysis.model_evaluation.ModelEvaluation`, a
pre-existing, framework-agnostic module -- no split needed, unlike Stage
10's ``ClusterDiscovery``) predicting a user-chosen discrete column (e.g.
``archetype``, ``v_ok_numeric``) from the run's numeric metrics, over one
run's persisted responses. Unlike Stages 7-10's pure read-only views, this
one runs real (cheap, local) computation per request -- but it's still
read-only over already-persisted data, no new writes.
"""

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.analysis.model_evaluation import ModelEvaluation
from web.plotting.model_evo_charts import build_model_evo_view
from web.plotting.render import set_chart_theme

router = APIRouter(prefix="/model_evo", tags=["model_evo"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()


def _possible_targets(df: pd.DataFrame) -> "list[str]":
    """Columns with 2-10 unique values and a non-float64 dtype -- the legacy tab's own target-column heuristic, preserved exactly."""
    return [col for col in df.columns if 2 <= df[col].nunique() <= 10 and df[col].dtype != "float64"]


def _targets_context(run_id: str) -> dict:
    """Load one run's responses and compute its candidate target columns, or an empty-state context if the run has none."""
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}

    df = pd.json_normalize(responses)
    return {
        "selected_run_id": run_id,
        "has_data": True,
        "possible_targets": _possible_targets(df),
    }


@router.get("", response_class=HTMLResponse)
def model_evo_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's target-column selector, if any runs exist."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_targets_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "model_evo.html", context)


@router.get("/targets", response_class=HTMLResponse)
def model_evo_targets(request: Request, run_id: str) -> HTMLResponse:
    """
    Return the ``#model-evo-targets`` fragment for one run -- used by the
    picker's htmx swap.

    Returns
    -------
    HTMLResponse
        200, with the target-column selector, if the run has persisted
        responses.
    HTMLResponse
        404, if the run has no persisted responses.
    """
    context = _targets_context(run_id)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_model_evo_targets.html", context, status_code=status_code)


@router.post("/evaluate", response_class=HTMLResponse)
async def model_evo_evaluate(request: Request) -> HTMLResponse:
    """
    Fit :class:`~core.analysis.model_evaluation.ModelEvaluation` for one
    run/target/test-size combination and return the
    ``#model-evo-results`` fragment.

    Returns
    -------
    HTMLResponse
        200, with the rendered metrics/confusion-matrix/feature-importance
        views, on success.
    HTMLResponse
        200, with an inline error message (dataset too small, target
        column missing, or any other ``ValueError`` from the underlying
        scikit-learn pipeline) -- a normal, expected outcome of a user's
        column/test-size choice against real data, not a server error, so
        it doesn't warrant a 4xx/5xx the way an unknown run id does.
    HTMLResponse
        404, if the run has no persisted responses.
    """
    set_chart_theme(request.cookies.get("nn_lab_theme", "dark"))
    form = await request.form()
    run_id = str(form.get("run_id", ""))
    target_column = str(form.get("target_column", ""))
    test_size = float(str(form.get("test_size", 0.2)))

    responses = _repository.load_responses(run_id)
    if not responses:
        return templates.TemplateResponse(
            request, "_model_evo_results.html", {"selected_run_id": run_id, "has_data": False}, status_code=404
        )

    df = pd.json_normalize(responses)
    try:
        results = ModelEvaluation(target_column=target_column).evaluate(df, test_size=test_size)
        view = build_model_evo_view(results)
        context = {"selected_run_id": run_id, "has_data": True, "error": None, **view}
    except ValueError as exc:
        context = {"selected_run_id": run_id, "has_data": True, "error": str(exc)}

    return templates.TemplateResponse(request, "_model_evo_results.html", context)
