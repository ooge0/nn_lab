"""
api.routers.status
=====================

Minimal service-status endpoint -- the FastAPI-era equivalent of the legacy
sidebar's Ollama/NLP green-red buttons (see
:mod:`core.services.status_checks` for what changed and why Neo4j is
deliberately excluded). Two representations of the same three checks (a
third, spaCy, added 2026-08-24): a plain JSON endpoint for programmatic/API
use, and an HTML fragment for the htmx widget embedded in the shared nav
(moved there from being ``/experiments``-only the same day) so "is Ollama
actually up" is visible on every page, not just before clicking Run.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.services.status_checks import check_nltk, check_ollama, check_spacy

router = APIRouter(prefix="/status", tags=["status"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _checks() -> list[dict]:
    return [check_ollama(), check_nltk(), check_spacy()]


@router.get("")
def status_json() -> dict:
    """
    Report Ollama/NLTK/spaCy reachability as JSON.

    Returns
    -------
    dict
        ``{"services": [{"name", "ok", "detail"}, ...], "all_ok": bool}``.
        Always 200 -- an unreachable *service* is a normal, expected
        outcome to report, not a server error, so a down Ollama shows up
        as ``ok: false`` in the body, not an HTTP error status.
    """
    services = _checks()
    return {"services": services, "all_ok": all(s["ok"] for s in services)}


@router.get("/widget", response_class=HTMLResponse)
def status_widget(request: Request) -> HTMLResponse:
    """Render the same checks as a small HTML fragment for htmx to embed."""
    return templates.TemplateResponse(request, "_status_widget.html", {"services": _checks()})
