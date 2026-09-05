"""
Shared Playwright E2E fixtures -- ``live_server`` runs the real FastAPI app in a background
thread so a real browser can make real HTTP requests against it (``TestClient`` never executes
JavaScript, which is the entire reason this suite exists -- see :mod:`tests.e2e.test_experiments_e2e`'s
module docstring). Session-scoped and shared across every file in this directory: pytest resolves
fixtures from the nearest ``conftest.py``, so one server instance serves the whole E2E session
regardless of how many test files use it, rather than each file starting its own.
"""

import socket
import threading
import time

import pytest
import uvicorn

from api.app import app

_PORT = 8791
_BASE_URL = f"http://127.0.0.1:{_PORT}"


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="session")
def live_server():
    """
    Run the real FastAPI app in a background thread for the duration of the E2E session. Uses a
    dedicated port (not 8000) so this never collides with a developer's own ``uvicorn --reload``
    session running alongside it.
    """
    config = uvicorn.Config(app, host="127.0.0.1", port=_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):  # up to ~10s for a cold import of the full router chain
        if _port_open(_PORT):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError(f"live_server did not start listening on port {_PORT} in time")

    yield _BASE_URL

    server.should_exit = True
    thread.join(timeout=5)
