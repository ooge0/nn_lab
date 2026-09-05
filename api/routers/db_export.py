"""
api.routers.db_export
========================

Wires :func:`core.services.db_export.export_run_to_db` to a page + an API call -- picks an
existing run (from the live ``JSONLStore``) and copies it into the real SQLite database
``operations.rst`` previously only showed as a hand-typed Python snippet. ``SQLiteRepo`` itself was
built and tested at Stage 3 but had no live endpoint until this router.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.services.db_export import DBExportError, export_run_to_db, get_sync_status

router = APIRouter(prefix="/db_export", tags=["db_export"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()


def _format_synced_at(iso_timestamp: Optional[str]) -> Optional[str]:
    """``SQLiteRepo.get_sync_status``'s raw ISO 8601 string, formatted for display -- ``None``
    (never exported) and a genuinely unparseable stored value both fall back to the raw input
    rather than raising, since this is a display concern, not something that should ever 500 the
    page over a formatting nicety.

    Date and time are separated by a literal newline (date on its own line, time+zone on the
    next) rather than a space -- paired with ``white-space: pre-line`` on the rendering element
    (``web/static/style.css``), this wraps the "Export status" column onto two lines without
    injecting a ``<br>`` (which Jinja2's autoescaping would otherwise render as literal text, not
    a real line break) or restructuring the table cell itself."""
    if not iso_timestamp:
        return None
    try:
        return datetime.fromisoformat(iso_timestamp).strftime("%Y-%m-%d\n%H:%M:%S UTC")
    except ValueError:
        return iso_timestamp


@router.get("", response_class=HTMLResponse)
async def db_export_page(request: Request) -> HTMLResponse:
    """Render every known run with a per-row "Send to DB" action and its last-sync status."""
    runs = _repository.list_runs()
    sync_status = {run_id: _format_synced_at(ts) for run_id, ts in get_sync_status().items()}
    return templates.TemplateResponse(request, "db_export.html", {"runs": runs, "sync_status": sync_status})


@router.post("/export", response_class=HTMLResponse)
async def export_run(request: Request, run_id: str, overwrite: bool = False) -> HTMLResponse:
    """
    Export one run's responses into ``results/nn_lab.db``, returning a small status fragment
    swapped into that run's row. ``overwrite=False`` (the default, a plain button click) reports a
    clear "already exported" message rather than silently duplicating rows; the page's own
    "Re-export" action retries with ``overwrite=True``. On success, the fragment also carries an
    out-of-band update for that row's "Export status" cell, so the newly-synced timestamp shows up
    immediately without a page reload.
    """
    try:
        result = export_run_to_db(_repository, run_id, overwrite=overwrite)
    except DBExportError as exc:
        return templates.TemplateResponse(
            request,
            "_db_export_status.html",
            {"run_id": run_id, "result": None, "error": str(exc), "synced_at": None},
        )
    return templates.TemplateResponse(
        request,
        "_db_export_status.html",
        {"run_id": run_id, "result": result, "error": None, "synced_at": _format_synced_at(result["synced_at"])},
    )
