"""
core.services.status_checks
==============================

Minimal service-reachability checks -- the FastAPI-era equivalent of the
legacy sidebar's three green/red buttons (:mod:`legacy.streamlit_app`,
``ensure_ollama_run``/``ensure_nltk_resources``/``Neo4jService
.ensure_neo4j_run``). Deliberately scoped to **Ollama + NLTK + spaCy only**:
Neo4j is excluded on purpose, per CLAUDE.md SS1 -- the whole Neo4j/knowledge-
graph subsystem stays "not even import-path-touched" until a separate future
plan, and wiring a new status check into it from this app would itself be
a new integration point into that untouched subsystem, not just a read.

``check_spacy`` added 2026-08-24 alongside ``core.analysis.syntactic_complexity``.
No stop/shutdown endpoint exists for any of these three, by deliberate choice:
NLTK and spaCy are not services at all (data files and an in-process library,
respectively -- there is nothing running to stop), and Ollama is the user's
own separately-managed process, likely shared with other uses outside this
app -- this app reads its status, it does not own its lifecycle.

All three checks are pure, side-effect-free, and safe to call on every page
load: unlike the legacy ``ensure_nltk_resources()`` (which silently
downloaded anything missing and therefore *always* returned ``True`` --
its own "NLP fail" branch was dead code, confirmed by reading it directly),
this module reports what is actually true right now and never mutates
local state as a side effect of being asked.
"""

from urllib.parse import urlsplit, urlunsplit

import nltk
import ollama
import spacy.util

from core.analysis.syntactic_complexity import SPACY_MODEL_NAME
from utils import config_loader_short

# Same resources CLAUDE.md SS11's documented dev setup (`tox.ini`) downloads
# before running the suite -- the single existing source of truth for "what
# this app's NLP pipeline actually needs," rather than inventing a second,
# possibly-drifting list.
_REQUIRED_NLTK_RESOURCES = ["vader_lexicon", "punkt", "punkt_tab", "brown", "averaged_perceptron_tagger_eng"]

# NLTK resource download IDs don't always match their nltk.data.find()
# lookup path -- verified empirically against a real local NLTK data dir,
# not assumed: vader_lexicon is stored zipped and nltk.data.find() only
# resolves it with the literal ".zip" suffix ("sentiment/vader_lexicon"
# alone raises LookupError even when the resource is genuinely installed).
_NLTK_FIND_PATHS = {
    "vader_lexicon": "sentiment/vader_lexicon.zip",
    "punkt": "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab",
    "brown": "corpora/brown",
    "averaged_perceptron_tagger_eng": "taggers/averaged_perceptron_tagger_eng",
}


def check_ollama() -> dict:
    """
    Check whether the local Ollama server is reachable.

    Reuses the same host :class:`core.adapters.ollama_client.OllamaClient`
    resolves (``config.ini``'s ``[OLLAMA] openai_base_url``, ``/v1``
    stripped) rather than a second, possibly-drifting config value.

    Returns
    -------
    dict
        ``{"name": "Ollama", "ok": bool, "detail": str}`` -- ``detail`` is
        a short human-readable reason on failure, or a model count on
        success.
    """
    parts = urlsplit(config_loader_short.OPENAI_BASE_URL)
    path = parts.path[: -len("/v1")] if parts.path.endswith("/v1") else parts.path
    host = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    try:
        models = ollama.Client(host=host).list()
        count = len(models.models)
        return {"name": "Ollama", "ok": True, "detail": f"{count} model(s) available"}
    except Exception as e:
        return {"name": "Ollama", "ok": False, "detail": f"{type(e).__name__}: {e}"}


def check_nltk() -> dict:
    """
    Check whether every NLTK resource this app's NLP pipeline needs is
    already downloaded locally -- does **not** download anything itself
    (unlike the legacy ``ensure_nltk_resources()``), so a missing resource
    is reported honestly rather than silently fixed and hidden.

    Returns
    -------
    dict
        ``{"name": "NLTK", "ok": bool, "detail": str}`` -- ``detail``
        names any missing resources, or confirms the count found.
    """
    missing = []
    for resource in _REQUIRED_NLTK_RESOURCES:
        try:
            nltk.data.find(_NLTK_FIND_PATHS[resource])
        except LookupError:
            missing.append(resource)

    if missing:
        return {"name": "NLTK", "ok": False, "detail": f"missing: {', '.join(missing)}"}
    return {"name": "NLTK", "ok": True, "detail": f"{len(_REQUIRED_NLTK_RESOURCES)} resource(s) found"}


def check_spacy() -> dict:
    """
    Check whether the spaCy model :func:`core.analysis.syntactic_complexity._get_nlp` loads needs
    is already downloaded locally -- does **not** download it (matching :func:`check_nltk`'s
    honest-not-silent convention), just reports whether ``python -m spacy download`` (README's
    setup step 5) has been run.

    Returns
    -------
    dict
        ``{"name": "spaCy", "ok": bool, "detail": str}``.
    """
    if SPACY_MODEL_NAME in spacy.util.get_installed_models():
        return {"name": "spaCy", "ok": True, "detail": f"{SPACY_MODEL_NAME} installed"}
    return {"name": "spaCy", "ok": False, "detail": f"{SPACY_MODEL_NAME} not installed"}
