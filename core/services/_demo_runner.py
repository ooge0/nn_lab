"""
core.services._demo_runner
===========================

Throwaway proof of the SSE + background-thread progress mechanism (Stage 1 of
the FastAPI rewrite). Contains no real business logic -- it exists solely to
de-risk the live-progress mechanism (replacing Streamlit's rerun model)
before it is entangled with real generation logic in Stage 5.

Notes
-----
Leading underscore in the module name marks it as throwaway: it is either
deleted or demoted to a documented reference once Stage 5 replaces it with
the real ``ExperimentRunner``.
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from core.services._sse import bridge_to_queue

__all__ = ["ProgressEvent", "bridge_to_queue", "DemoRunner", "demo_runner"]


@dataclass
class ProgressEvent:
    """
    A single progress update pushed from the background thread to the SSE
    stream.

    Parameters
    ----------
    step : int
        The current step number (1-indexed).
    total : int
        The total number of steps in the run.
    done : bool, optional
        ``True`` on the terminal event that closes the stream (default
        ``False``).
    """

    step: int
    total: int
    done: bool = False


class DemoRunner:
    """
    Runs a trivial counted loop on a background daemon thread, streaming
    progress back through an ``asyncio.Queue`` via :func:`bridge_to_queue`.

    Enforces the single-user/single-session concurrent-run guard required by
    the project's deployment constraints: a second concurrent run is
    rejected rather than queued.

    Parameters
    ----------
    total_steps : int, optional
        Number of steps the dummy loop counts through (default ``10``).
    delay_seconds : float, optional
        Delay between steps, in seconds (default ``0.3``).
    """

    def __init__(self, total_steps: int = 10, delay_seconds: float = 0.3) -> None:
        self.total_steps = total_steps
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self._running = False
        self._queue: Optional["asyncio.Queue[ProgressEvent]"] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        """bool: Whether a run is currently in progress."""
        with self._lock:
            return self._running

    @property
    def queue(self) -> Optional["asyncio.Queue[ProgressEvent]"]:
        """Optional[asyncio.Queue[ProgressEvent]]: The active run's queue, or ``None`` if no run has started."""
        return self._queue

    def try_start(self, loop: asyncio.AbstractEventLoop) -> Optional["asyncio.Queue[ProgressEvent]"]:
        """
        Attempt to start a new run (the concurrent-run guard).

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop of the request that is starting the run; passed
            through to the background thread so it can bridge progress
            events back via :func:`bridge_to_queue`.

        Returns
        -------
        Optional[asyncio.Queue[ProgressEvent]]
            A fresh queue for the new run, or ``None`` if a run was already
            in progress (the caller should reject the request, e.g. with
            HTTP 409).
        """
        with self._lock:
            if self._running:
                return None
            self._running = True
            self._queue = asyncio.Queue()
            queue = self._queue

        self._thread = threading.Thread(target=self._run, args=(loop, queue), daemon=True)
        self._thread.start()
        return queue

    def _run(self, loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[ProgressEvent]") -> None:
        """
        Background-thread body: counts to ``total_steps``; the last step's
        event is the terminal one.

        Notes
        -----
        If the owning event loop closes mid-run (e.g. the server is shutting
        down -- the Ctrl+C case), ``bridge_to_queue`` raises ``RuntimeError``.
        Nobody can still be listening once the loop is gone, so this is
        caught and logged rather than left as an unhandled thread exception;
        the ``finally`` block still runs either way, so the guard always
        clears.
        """
        try:
            for step in range(1, self.total_steps + 1):
                time.sleep(self.delay_seconds)
                bridge_to_queue(
                    loop, queue, ProgressEvent(step=step, total=self.total_steps, done=step == self.total_steps)
                )
        except RuntimeError as exc:
            logger.debug(f"DemoRunner: stopping early, event loop closed mid-run ({exc}).")
        finally:
            with self._lock:
                self._running = False


demo_runner = DemoRunner()
"""DemoRunner: module-level singleton -- single-user/single-session per project constraints."""
