"""
api.routers.runs
===================

Stage 7 -- ``tab_perf`` parity. Read-only aggregation/rendering over
already-persisted runs (Stage 6's ``ExperimentRunner`` output): a run
picker plus a per-run performance summary. No generation, no SSE -- proves
the read-side API/web pattern now that the write side is settled.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.services.metrics_engine import MetricsEngine, RunNotFoundError

router = APIRouter(prefix="/runs", tags=["runs"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()
_metrics_engine = MetricsEngine(_repository)


@router.get("", response_class=HTMLResponse)
async def runs_page(request: Request) -> HTMLResponse:
    """
    Render the run picker plus the most recently started run's summary, if any runs exist.

    Notes
    -----
    A real 500 was found here (not hypothetical): a run whose ``.meta.json`` exists but whose
    response ``.jsonl`` is empty or missing (a JSONLStore run record with zero persisted
    responses -- e.g. a crashed/killed run, or a leftover test fixture) made ``summarize_run``
    raise ``RunNotFoundError`` completely unguarded here, taking down the whole page -- even
    though the sibling ``/runs/summary`` endpoint two lines below already handles this exact case
    gracefully. Fixed to match that existing precedent instead of leaving the two endpoints
    inconsistent.
    """
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    summary = None
    if selected_run_id is not None:
        try:
            summary = _metrics_engine.summarize_run(selected_run_id)
        except RunNotFoundError:
            summary = None
    return templates.TemplateResponse(
        request,
        "perf.html",
        {"runs": runs, "selected_run_id": selected_run_id, "summary": summary},
    )


@router.get("/summary", response_class=HTMLResponse)
async def run_summary(request: Request, run_id: str) -> HTMLResponse:
    """Return the ``#perf-summary`` fragment for one run -- used by the picker's htmx swap (``run_id`` as a query param, so a plain ``<select name="run_id">`` can drive it with no extra JS)."""
    try:
        summary = _metrics_engine.summarize_run(run_id)
    except RunNotFoundError:
        return templates.TemplateResponse(
            request, "_perf_summary.html", {"selected_run_id": run_id, "summary": None}, status_code=404
        )
    return templates.TemplateResponse(request, "_perf_summary.html", {"selected_run_id": run_id, "summary": summary})


@router.get("/judging_comparison", response_class=HTMLResponse)
async def judging_comparison(request: Request, run_id_a: str, run_id_b: str) -> HTMLResponse:
    """
    Return the ``#judging-comparison`` fragment: pass-rate delta between two runs -- built for
    comparing a self-critic run against a teacher-judged run (CLAUDE.md SS4), but works for any two
    run IDs. Used by the ``/runs`` page's two-run picker via htmx.
    """
    try:
        comparison = _metrics_engine.compare_judging_modes(run_id_a, run_id_b)
    except RunNotFoundError as exc:
        return templates.TemplateResponse(
            request,
            "_judging_comparison.html",
            {"comparison": None, "error": str(exc)},
            status_code=404,
        )
    return templates.TemplateResponse(request, "_judging_comparison.html", {"comparison": comparison, "error": None})
