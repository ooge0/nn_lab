"""
api.routers.demo
=================

Throwaway Stage 1 endpoints proving the SSE + background-thread live-progress
mechanism end-to-end, ahead of any real generation logic (Stage 5). See
:mod:`core.services._demo_runner` for the mechanism itself.
"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.services._demo_runner import demo_runner

router = APIRouter(prefix="/demo", tags=["demo"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
async def demo_page(request: Request) -> HTMLResponse:
    """Render the demo page: a start button and an htmx SSE-driven progress view."""
    return templates.TemplateResponse(request, "demo.html", {"total_steps": demo_runner.total_steps})


@router.post("/start", response_class=HTMLResponse)
async def demo_start(request: Request) -> HTMLResponse:
    """
    Start a demo run and return the SSE-connecting fragment for htmx to swap in.

    The run is already started (thread launched, queue created) before this
    response is sent, so no progress events can be missed: `asyncio.Queue`
    buffers them until `/demo/stream` connects and starts consuming, even if
    that happens a moment after this response returns.

    Returns
    -------
    HTMLResponse
        202, with the ``hx-ext="sse"`` fragment, on success.
    HTMLResponse
        409, with an inline error message, if a run is already in progress
        (the concurrent-run guard -- single-user/single-session per the
        project's deployment constraints).
    """
    loop = asyncio.get_running_loop()
    queue = demo_runner.try_start(loop)
    if queue is None:
        return templates.TemplateResponse(
            request, "_demo_fragment.html", {"error": "A demo run is already in progress."}, status_code=409
        )
    return templates.TemplateResponse(
        request, "_demo_fragment.html", {"error": None, "total_steps": demo_runner.total_steps}, status_code=202
    )


@router.get("/stream", response_class=EventSourceResponse)
async def demo_stream():
    """
    Stream progress events for the current (or most recently started) run.

    Yields
    ------
    ServerSentEvent
        One ``progress`` event per step (raw HTML fragment for htmx's
        ``sse-swap`` to inject directly), followed by one ``progress-done``
        event with an empty payload once the run finishes -- htmx's
        ``sse-close`` attribute listens for that event name to close the
        client-side connection deliberately, avoiding the default
        `EventSource` auto-reconnect that would otherwise fire when the
        server closes the stream. If no run has ever been started, a single
        ``error`` event is sent instead and the stream closes immediately.
    """
    queue = demo_runner.queue
    if queue is None:
        yield ServerSentEvent(event="error", raw_data="No active run. POST /demo/start first.")
        return

    while True:
        item = await queue.get()
        suffix = " -- done" if item.done else ""
        yield ServerSentEvent(
            event="progress",
            raw_data=f'<div id="demo-progress">Step {item.step} / {item.total}{suffix}</div>',
        )
        if item.done:
            yield ServerSentEvent(event="progress-done", raw_data="")
            break
