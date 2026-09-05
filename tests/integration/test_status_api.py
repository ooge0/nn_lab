"""
Functional API tests for the ``/status`` endpoint
(:mod:`api.routers.status`) -- through the real FastAPI app, with the
underlying :func:`core.services.status_checks.check_ollama`/``check_nltk``/``check_spacy``
swapped for deterministic fakes so this suite doesn't depend on a real
local Ollama server, NLTK data directory, or spaCy model being present.
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.status as status_router
from api.app import app


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fake_checks(monkeypatch):
    """Deterministic Ollama=ok / NLTK=down / spaCy=ok fixture, wired for every test in this module."""
    monkeypatch.setattr(
        status_router, "check_ollama", lambda: {"name": "Ollama", "ok": True, "detail": "3 model(s) available"}
    )
    monkeypatch.setattr(
        status_router, "check_nltk", lambda: {"name": "NLTK", "ok": False, "detail": "missing: vader_lexicon"}
    )
    monkeypatch.setattr(
        status_router, "check_spacy", lambda: {"name": "spaCy", "ok": True, "detail": "en_core_web_sm installed"}
    )


def test_status_json_reports_all_three_services_and_an_overall_flag(client):
    """GET /status returns all three checks verbatim plus an all_ok flag that is False when any one service is down."""
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["services"] == [
        {"name": "Ollama", "ok": True, "detail": "3 model(s) available"},
        {"name": "NLTK", "ok": False, "detail": "missing: vader_lexicon"},
        {"name": "spaCy", "ok": True, "detail": "en_core_web_sm installed"},
    ]
    assert body["all_ok"] is False


def test_status_json_all_ok_true_when_every_service_is_up(client, monkeypatch):
    """all_ok flips to True only when every service reports ok."""
    monkeypatch.setattr(
        status_router, "check_nltk", lambda: {"name": "NLTK", "ok": True, "detail": "5 resource(s) found"}
    )
    response = client.get("/status")
    assert response.json()["all_ok"] is True


def test_status_json_all_ok_false_when_only_spacy_is_down(client, monkeypatch):
    """A down spaCy alone (Ollama/NLTK both up) is enough to flip all_ok to False -- confirms spaCy is a real
    part of the aggregate, not just appended to the list without affecting the flag."""
    monkeypatch.setattr(
        status_router, "check_nltk", lambda: {"name": "NLTK", "ok": True, "detail": "5 resource(s) found"}
    )
    monkeypatch.setattr(
        status_router, "check_spacy", lambda: {"name": "spaCy", "ok": False, "detail": "en_core_web_sm not installed"}
    )
    response = client.get("/status")
    assert response.json()["all_ok"] is False


def test_status_widget_renders_a_badge_per_service_with_ok_fail_classes(client):
    """GET /status/widget renders one badge per service, with the ok/fail CSS class and a human-readable label matching each check's actual state."""
    response = client.get("/status/widget")
    assert response.status_code == 200
    assert "status-ok" in response.text
    assert "status-fail" in response.text
    # Ties each service's own fixture detail string to its badge class, so this still
    # proves per-service class association now that the badge carries no separate
    # ok/fail glyph (the project disallows decorative emoji in the UI).
    assert 'status-ok" title="3 model(s) available"' in response.text
    assert "Ollama" in response.text
    assert 'status-fail" title="missing: vader_lexicon"' in response.text
    assert "NLTK" in response.text
    assert "spaCy" in response.text
