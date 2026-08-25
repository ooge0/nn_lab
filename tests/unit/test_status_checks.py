"""
Unit tests for :mod:`core.services.status_checks` -- the minimal
Ollama/NLTK/spaCy reachability checks that replace the legacy sidebar's
green/red buttons (Neo4j deliberately excluded, see the module docstring
for why). No real network/filesystem: ``ollama.Client``/``nltk.data.find``/
``spacy.util.get_installed_models`` are monkeypatched so these run fast and
deterministically regardless of whether a real Ollama server, NLTK data
directory, or spaCy model is present.
"""

import nltk
import ollama
import spacy.util

from core.services.status_checks import SPACY_MODEL_NAME, check_nltk, check_ollama, check_spacy


class _FakeModel:
    def __init__(self, name):
        self.model = name


class _FakeListResponse:
    def __init__(self, model_names):
        self.models = [_FakeModel(n) for n in model_names]


class _FakeOllamaClient:
    def __init__(self, models=None, error=None):
        self._models = models or []
        self._error = error

    def list(self):
        if self._error:
            raise self._error
        return _FakeListResponse(self._models)


def test_check_ollama_reports_ok_with_model_count_when_reachable(monkeypatch):
    """A reachable Ollama server reports ok=True and the real model count in detail."""
    monkeypatch.setattr(ollama, "Client", lambda host: _FakeOllamaClient(models=["a:latest", "b:latest"]))
    result = check_ollama()
    assert result == {"name": "Ollama", "ok": True, "detail": "2 model(s) available"}


def test_check_ollama_reports_failure_reason_when_unreachable(monkeypatch):
    """A connection failure is caught and reported as ok=False with the real exception type/message, not raised."""
    monkeypatch.setattr(ollama, "Client", lambda host: _FakeOllamaClient(error=ConnectionError("refused")))
    result = check_ollama()
    assert result["name"] == "Ollama"
    assert result["ok"] is False
    assert "ConnectionError" in result["detail"]
    assert "refused" in result["detail"]


def test_check_nltk_reports_ok_when_every_resource_is_found(monkeypatch):
    """All 5 required resources found -> ok=True."""
    monkeypatch.setattr(nltk.data, "find", lambda path: "found")
    result = check_nltk()
    assert result == {"name": "NLTK", "ok": True, "detail": "5 resource(s) found"}


def test_check_nltk_reports_which_resources_are_missing_without_downloading(monkeypatch):
    """
    Missing resources are named in detail, not silently downloaded -- a
    deliberate improvement over the legacy ``ensure_nltk_resources()``,
    whose auto-download meant its own failure branch was unreachable dead
    code (it always returned True). This function never calls
    ``nltk.download`` at all.
    """
    calls = []

    def fake_find(path):
        calls.append(path)
        if "vader_lexicon" in path:
            raise LookupError("not found")
        return "found"

    monkeypatch.setattr(nltk.data, "find", fake_find)
    monkeypatch.setattr(
        nltk, "download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not auto-download"))
    )

    result = check_nltk()
    assert result["ok"] is False
    assert "vader_lexicon" in result["detail"]


def test_check_spacy_reports_ok_when_model_is_installed(monkeypatch):
    monkeypatch.setattr(spacy.util, "get_installed_models", lambda: [SPACY_MODEL_NAME])
    result = check_spacy()
    assert result == {"name": "spaCy", "ok": True, "detail": f"{SPACY_MODEL_NAME} installed"}


def test_check_spacy_reports_not_installed_without_downloading(monkeypatch):
    """Missing model is named in detail, not silently downloaded -- matches check_nltk's honest-not-silent convention."""
    monkeypatch.setattr(spacy.util, "get_installed_models", lambda: [])
    result = check_spacy()
    assert result == {"name": "spaCy", "ok": False, "detail": f"{SPACY_MODEL_NAME} not installed"}
