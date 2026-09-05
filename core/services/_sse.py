"""
core.services._sse
=====================

The one line that crosses the worker-thread/event-loop boundary for every
background-thread-driven SSE mechanism in this project. Extracted here so
:mod:`core.services._demo_runner` (Stage 1's proof of the mechanism) and
:mod:`core.services.experiment_runner` (Stage 5's real use of it) share the
same tested implementation instead of each carrying their own copy.
"""

import asyncio
from typing import Any


def bridge_to_queue(loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[Any]", event: Any) -> None:
    """
    Thread-safe bridge: schedule ``event`` onto ``queue`` from any thread.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop that owns ``queue`` (the loop running the FastAPI
        request that created it).
    queue : asyncio.Queue
        The queue an SSE endpoint is consuming from.
    event : Any
        The event to enqueue.

    Notes
    -----
    ``asyncio.Queue`` is not thread-safe on its own -- ``put_nowait`` must
    be scheduled back onto the owning loop via ``call_soon_threadsafe``
    when called from a worker thread.
    """
    loop.call_soon_threadsafe(queue.put_nowait, event)
