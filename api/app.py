"""
api.app
=======

FastAPI application factory. Run locally with::

    uvicorn api.app:app --reload

Wires the throwaway ``demo`` router (Stage 1), ``experiments``
(Stages 5-6), and ``runs`` (Stage 7); later stages add ``analytics``,
``clusters``, etc. (see the project's refactor plan, Stage 8 onward).

**Logging (CLAUDE.md SS7's standing "loguru across the app" requirement, wired up for real
2026-09-05):** until now, ``loguru`` was imported and configured only in the legacy Streamlit
scripts (``legacy/streamlit_app.py`` and its variants) -- the FastAPI app had zero persistent
logging, a real, previously-disclosed gap (see ``docs/source/wiki/00-getting-started.rst``'s
troubleshooting section). This module now adds a file sink at import time (once, regardless of
which entry point imports it -- ``uvicorn``, the test suite via ``TestClient``, or a script), reusing
the exact same ``logs/<log_file_entry>`` path and rotation/retention settings the legacy scripts
already established, so both eras write to the same place with the same convention. Deliberately
does **not** call ``logger.remove()`` first (unlike the legacy scripts) -- that would strip loguru's
own default stderr sink, and the actual reported problem was "I don't see any logs at all," not
"I see them in the wrong place"; keeping the console sink means a live ``uvicorn --reload`` session
still shows log lines directly in the terminal, in addition to the persistent file.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from api._paths import STATIC_DIR, TEMPLATES_DIR
from api.routers import (
    analytics,
    api_status,
    benchmark,
    clusters,
    db_export,
    demo,
    experiments,
    faq,
    knowledge_graph,
    model_evo,
    monitor,
    nlp,
    runs,
    status,
)
from utils import config_loader_short

_LOG_FILE = config_loader_short.LOGS_DIR / config_loader_short.LOG_FILE_ENTRY.name
logger.add(
    _LOG_FILE,
    rotation="10 MB",
    retention="10 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
)

_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app() -> FastAPI:
    """
    Build and return the FastAPI application instance.

    Returns
    -------
    fastapi.FastAPI
        The configured app, with all routers included and static files
        mounted under ``/static``.
    """
    app = FastAPI(title="nn_lab")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(demo.router)
    app.include_router(experiments.router)
    app.include_router(runs.router)
    app.include_router(analytics.router)
    app.include_router(nlp.router)
    app.include_router(clusters.router)
    app.include_router(model_evo.router)
    app.include_router(benchmark.router)
    app.include_router(faq.router)
    app.include_router(monitor.router)
    app.include_router(status.router)
    app.include_router(db_export.router)
    app.include_router(api_status.router)
    app.include_router(knowledge_graph.router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Landing page -- links to every reachable page. There is no other navigation entry point, so ``/`` had 404'd until this was added."""
        return _templates.TemplateResponse(request, "index.html", {})

    logger.info(f"nn_lab FastAPI app created -- logging to {_LOG_FILE}")
    return app


app = create_app()
