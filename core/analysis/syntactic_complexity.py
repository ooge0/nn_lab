"""
syntactic_complexity.py

``dependency_distance`` -- mean syntactic dependency-tree distance between related token pairs, via
spaCy + TextDescriptives' ``textdescriptives/dependency_distance`` pipeline component. A validated
complexity/intellectualization marker (Oakes 2017, Lu 2010): longer average dependency distance
means a syntactically deeper, more structurally complex sentence, independent of raw sentence
length. The project's existing ``avg_sentence_length`` (word count / sentence count) is a much
cruder proxy for the same underlying idea -- it says nothing about grammatical structure, only
verbosity.

Added 2026-08-24. CLAUDE.md SS7 states a preference for validated libraries
(``textdescriptives``/``lexicalrichness``) over hand-rolled metric code, but neither had actually
been adopted anywhere in the codebase until this module -- both were named as intent, not wired in.

The spaCy pipeline is loaded lazily, once per process, matching
:func:`core.analysis.calculate_advanced_linguistic_metrics._get_embedder`'s own pattern for the
sentence-embedding model -- model loading is the expensive part, not the per-call computation.
"""

import math
from typing import Optional

import spacy
import textdescriptives  # noqa: F401 -- import registers the "textdescriptives/*" spaCy pipe factories
from spacy.language import Language

SPACY_MODEL_NAME = "en_core_web_sm"
_nlp: Optional[Language] = None


def _get_nlp() -> Language:
    """Lazily construct (once per process) and return the shared spaCy pipeline."""
    global _nlp
    if _nlp is None:
        nlp = spacy.load(SPACY_MODEL_NAME)
        nlp.add_pipe("textdescriptives/dependency_distance")
        _nlp = nlp
    return _nlp


def dependency_distance(text: str) -> float:
    """
    Mean dependency-tree distance between syntactically related token pairs.

    Parameters
    ----------
    text : str
        The text to analyze.

    Returns
    -------
    float
        Rounded to 3 decimals. ``0.0`` for empty/whitespace-only text or text with no dependency
        relations (e.g. a single punctuation token) -- TextDescriptives itself returns ``NaN`` for
        these degenerate cases, which this function replaces with the same "no signal" convention
        every other metric in this project uses (matching ``PsychScientist``'s own empty-input
        guards) rather than letting a ``NaN`` propagate into a persisted JSONL record.
    """
    if not text or not text.strip():
        return 0.0
    doc = _get_nlp()(text)
    value = doc._.dependency_distance["dependency_distance_mean"]
    if value is None or math.isnan(value):
        return 0.0
    return round(float(value), 3)
