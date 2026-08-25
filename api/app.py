"""
api.app
=======

FastAPI application factory. Run locally with::

    uvicorn api.app:app --reload

Wires the throwaway ``demo`` router (Stage 1), ``experiments``
(Stages 5-6), and ``runs`` (Stage 7); later stages add ``analytics``,
``clusters``, etc. (see the project's refactor plan, Stage 8 onward).
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
    model_evo,
    monitor,
    nlp,
    runs,
    status,
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

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Landing page -- links to every reachable page. There is no other navigation entry point, so ``/`` had 404'd until this was added."""
        return _templates.TemplateResponse(request, "index.html", {})

    return app


app = create_app()
