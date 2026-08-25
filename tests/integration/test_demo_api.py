"""
Functional API tests for the Stage 1 SSE + background-thread demo
(:mod:`api.routers.demo`) -- proving the mechanism end-to-end through the
real FastAPI app, not just its isolated helper (see
``test_demo_queue_bridge.py`` for that).
"""

import time

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.services._demo_runner import demo_runner


@pytest.fixture
def client():
    """A `TestClient` used as a context manager, so every request in a test shares one event loop.

    Without the `with` block, Starlette's TestClient is not guaranteed to reuse
    the same loop across separate calls -- and this mechanism specifically
    depends on that: `/demo/start` captures `asyncio.get_running_loop()` and
    hands it to the background thread, which schedules progress events back
    onto *that* loop via `call_soon_threadsafe`. If `/demo/stream` then ran on
    a *different* loop, its `queue.get()` would wait forever for events
    scheduled on a loop nobody is running anymore.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fast_demo_runner():
    """Shrink the run to a few fast steps for tests, and wait out any run left in-flight by a previous test."""
    original_total, original_delay = demo_runner.total_steps, demo_runner.delay_seconds
    demo_runner.total_steps, demo_runner.delay_seconds = 4, 0.05
    yield
    deadline = time.time() + 5
    while demo_runner.running and time.time() < deadline:
        time.sleep(0.02)
    demo_runner.total_steps, demo_runner.delay_seconds = original_total, original_delay


def test_start_returns_202_with_sse_fragment(client):
    """POST /demo/start launches a run and returns the htmx SSE-connect fragment."""
    response = client.post("/demo/start")
    assert response.status_code == 202
    assert 'sse-connect="/demo/stream"' in response.text
    assert 'sse-close="progress-done"' in response.text


def test_second_concurrent_start_is_rejected(client):
    """A second POST /demo/start while one is in flight is rejected with 409 (the concurrent-run guard)."""
    first = client.post("/demo/start")
    assert first.status_code == 202

    second = client.post("/demo/start")
    assert second.status_code == 409
    assert "already in progress" in second.text


def test_stream_yields_all_progress_events_in_order_then_closes(client):
    """GET /demo/stream, after a start, yields exactly N ordered progress events then progress-done."""
    started = client.post("/demo/start")
    assert started.status_code == 202

    events = []
    with client.stream("GET", "/demo/stream") as response:
        assert response.status_code == 200
        event_name = None
        for line in response.iter_lines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event_name is not None:
                events.append((event_name, line.split(":", 1)[1].strip()))
                if event_name == "progress-done":
                    break
                event_name = None

    progress_events = [e for e in events if e[0] == "progress"]
    close_events = [e for e in events if e[0] == "progress-done"]

    assert len(progress_events) == demo_runner.total_steps
    for i, (_, data) in enumerate(progress_events, start=1):
        assert f"Step {i} / {demo_runner.total_steps}" in data
    assert "done" in progress_events[-1][1]
    assert len(close_events) == 1


def test_stream_without_a_started_run_sends_error_and_closes(client):
    """GET /demo/stream with no run ever started sends a single error event, not a hang."""
    demo_runner._queue = None  # simulate "never started" regardless of test execution order
    with client.stream("GET", "/demo/stream") as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]
    assert any(line == "event: error" for line in lines)
