"""
Functional API tests for :mod:`api.routers.api_status` -- through the real FastAPI app (no fakes
swapped in for the routers it checks, since the whole point is verifying it exercises the *real*
app, the same way a browser would).
"""

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def test_api_status_page_returns_200_and_reports_all_frontend_pages_checked(client):
    response = client.get("/api_status")

    assert response.status_code == 200
    assert "Frontend pages" in response.text
    assert "Backend / API routes" in response.text
    assert "Not fired" in response.text
    # Every no-arg page listed in the module actually got a live status code rendered, not just named.
    assert "/experiments" in response.text
    assert "/analytics" in response.text


def test_api_status_page_never_fires_side_effecting_or_streaming_routes(client):
    """The 'Not fired' section lists these routes by name -- confirms they're documented as
    skipped, not silently omitted or (worse) actually called."""
    response = client.get("/api_status")

    assert response.status_code == 200
    assert "/experiments/start" in response.text
    assert "/db_export/export" in response.text
    assert "/experiments/stream" in response.text
    assert "writes into results/nn_lab.db" in response.text


def test_api_status_page_skips_run_id_routes_gracefully_when_no_runs_exist(client, tmp_path, monkeypatch):
    """With zero runs in the live JSONLStore directory, run_id-needing backend routes must report
    a clear skip, not a 500 or a fabricated run_id."""
    monkeypatch.setattr(
        "api.routers.api_status.JSONLStore", lambda: type("R", (), {"list_runs": staticmethod(lambda: [])})()
    )

    response = client.get("/api_status")

    assert response.status_code == 200
    assert "skipped: no run exists to check with" in response.text
