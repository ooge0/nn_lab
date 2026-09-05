"""
Unit tests for :func:`core.services._demo_runner.bridge_to_queue` in
isolation -- the one line in Stage 1's SSE mechanism that actually crosses
the worker-thread/event-loop boundary.
"""

import asyncio
import threading

from core.services._demo_runner import ProgressEvent, bridge_to_queue


def test_bridge_to_queue_delivers_event_from_another_thread():
    """An event pushed from a plain worker thread arrives on the loop-owned queue."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue[ProgressEvent]" = asyncio.Queue()
        event = ProgressEvent(step=3, total=10)

        worker = threading.Thread(target=bridge_to_queue, args=(loop, queue, event))
        worker.start()
        worker.join()

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received is event

    asyncio.run(scenario())


def test_bridge_to_queue_preserves_order():
    """Multiple events pushed from a worker thread arrive on the queue in push order."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue[ProgressEvent]" = asyncio.Queue()
        events = [ProgressEvent(step=i, total=5) for i in range(1, 6)]

        def worker() -> None:
            for event in events:
                bridge_to_queue(loop, queue, event)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        received = [await asyncio.wait_for(queue.get(), timeout=1.0) for _ in events]
        assert received == events

    asyncio.run(scenario())


def test_bridge_to_queue_is_a_thin_wrapper_over_call_soon_threadsafe():
    """bridge_to_queue does nothing but schedule queue.put_nowait via call_soon_threadsafe."""

    calls = []

    class FakeLoop:
        def call_soon_threadsafe(self, callback, *args):
            calls.append((callback, args))

    class FakeQueue:
        def put_nowait(self, item):
            pass

    loop = FakeLoop()
    queue = FakeQueue()
    event = ProgressEvent(step=1, total=1)

    bridge_to_queue(loop, queue, event)

    assert calls == [(queue.put_nowait, (event,))]
