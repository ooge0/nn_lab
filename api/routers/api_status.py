"""
api.routers.api_status
=========================

``GET /api_status`` -- one page that actually calls every safe (read-only, no side effects) route
in the app right now and reports its real, live status, split into **Frontend pages** (the HTML
pages reachable from the nav -- what would otherwise mean clicking through one at a time) and
**Backend / API routes** (the fragment endpoints those pages call internally via htmx). Built
directly in response to a real, recurring pain point: a 500 on ``/runs`` (2026-08-25) was only
found by manually clicking into it, with no way to check every page at once.

Uses a real in-process :class:`~fastapi.testclient.TestClient` bound to ``request.app`` (not a
module-level import of the app -- that would be a circular import, since ``api.app`` is what
includes this router) to call each route exactly as a browser or ``curl`` would --
``raise_server_exceptions=False`` so a real 500 is reported as a status code here, not raised
into and crashing this health-check page itself. A failure shown here is a real failure for a
real user too, not a mock or a static assumption.

Side-effecting routes (starting/stopping an experiment, exporting to DB, the two SSE streams) are
deliberately **listed, not fired** -- this page must never itself trigger a real generation run or
duplicate a database export as a side effect of checking whether the app is healthy.
"""

import time
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore

router = APIRouter(prefix="/api_status", tags=["api_status"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# (label, path) -- every no-arg GET page reachable from the sidebar nav, plus the landing page and
# the auto-generated API docs. Checked with no query params, matching a first, cold click.
_FRONTEND_PAGES = [
    ("Landing page", "/"),
    ("Generation", "/experiments"),
    ("Performance", "/runs"),
    ("Analytics", "/analytics"),
    ("NLP Science", "/nlp"),
    ("Clustering", "/clusters"),
    ("Model Evaluation", "/model_evo"),
    ("Benchmark", "/benchmark"),
    ("System Monitor", "/monitor"),
    ("Export to DB", "/db_export"),
    ("FAQ", "/faq"),
    ("Swagger (API docs)", "/docs"),
    ("ReDoc (API docs)", "/redoc"),
]

# (label, path, needs_run_id) -- read-only fragment routes the pages above call via htmx. Checked
# for real when needs_run_id is True and at least one run exists (the most recently started run's
# id is used); otherwise reported as skipped, never guessed at with a fake id.
_BACKEND_READONLY_ROUTES = [
    ("Service status (JSON)", "/status", False),
    ("Service status widget", "/status/widget", False),
    ("Run summary fragment", "/runs/summary", True),
    ("Analytics charts", "/analytics/charts", True),
    ("NLP charts", "/nlp/charts", True),
    ("Cluster charts", "/clusters/charts", True),
    ("Model evaluation targets", "/model_evo/targets", True),
    ("Benchmark report", "/benchmark/report", True),
    ("Monitor schema", "/monitor/schema", True),
]

# (label, method, path, reason) -- deliberately not fired; see module docstring.
_BACKEND_SIDE_EFFECTING_ROUTES = [
    ("Export to DB", "POST", "/db_export/export", "writes into results/nn_lab.db"),
    ("Start experiment", "POST", "/experiments/start", "starts a real generation run"),
    ("Stop experiment", "POST", "/experiments/stop", "stops a real in-progress run"),
    ("Experiment preview", "POST", "/experiments/preview", "not side-effecting, but needs a full form body"),
    ("Experiment progress stream", "GET", "/experiments/stream", "Server-Sent Events, never terminates"),
    ("Demo progress stream", "GET", "/demo/stream", "Server-Sent Events, never terminates"),
    ("Judging-mode comparison", "GET", "/runs/judging_comparison", "needs two distinct run_ids, not one"),
]


def _check(client: TestClient, path: str, params: Optional[dict] = None) -> dict:
    start = time.monotonic()
    try:
        response = client.get(path, params=params)
        return {
            "path": path,
            "checked": True,
            "ok": response.status_code < 400,
            "status_code": response.status_code,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
            "detail": None,
        }
    except Exception as exc:
        return {
            "path": path,
            "checked": True,
            "ok": False,
            "status_code": None,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
            "detail": f"{type(exc).__name__}: {exc}",
        }


@router.get("", response_class=HTMLResponse)
async def api_status_page(request: Request) -> HTMLResponse:
    """Live-check every safe route and render the results, grouped frontend/backend."""
    runs = JSONLStore().list_runs()
    latest_run_id = runs[0].run_id if runs else None

    with TestClient(request.app, raise_server_exceptions=False) as client:
        frontend_results = [{"label": label, **_check(client, path)} for label, path in _FRONTEND_PAGES]

        backend_results = []
        for label, path, needs_run_id in _BACKEND_READONLY_ROUTES:
            if needs_run_id and latest_run_id is None:
                backend_results.append(
                    {
                        "label": label,
                        "path": path,
                        "checked": False,
                        "ok": None,
                        "detail": "skipped: no run exists to check with",
                    }
                )
            else:
                params = {"run_id": latest_run_id} if needs_run_id else None
                backend_results.append({"label": label, **_check(client, path, params)})

    not_fired = [
        {"label": label, "method": method, "path": path, "reason": reason}
        for label, method, path, reason in _BACKEND_SIDE_EFFECTING_ROUTES
    ]

    all_checked_ok = all(r["ok"] for r in frontend_results) and all(r["ok"] for r in backend_results if r["checked"])

    return templates.TemplateResponse(
        request,
        "api_status.html",
        {
            "frontend_results": frontend_results,
            "backend_results": backend_results,
            "not_fired": not_fired,
            "latest_run_id": latest_run_id,
            "all_checked_ok": all_checked_ok,
        },
    )
