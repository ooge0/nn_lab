"""
hallucination_check.py

Layer 2 of the per-response cascade (CLAUDE.md SS3a: "NLI for factual contradiction") -- checks
whether a response contradicts the RAG-retrieved context it was generated against, using a local
NLI cross-encoder.

**Only meaningful when RAG is enabled.** For this project's archetype-conditioned style-rewriting
task, there is no general-purpose ground-truth document to check "hallucination" against in the
non-RAG case -- the only real, defensible source of "what the response should be consistent with"
is the knowledge-base context RAG itself retrieves. When RAG is disabled for a run, this check is
skipped entirely and reported as not applicable (``checked: False``), not silently passed as
``ok``.

Uses ``cross-encoder/nli-MiniLM2-L6-H768`` (same MiniLM family as ``all-MiniLM-L6-v2``, already used
elsewhere in this project for embeddings -- small, CPU-friendly, no paid API, matching the "weak
machine" constraint the author set for the Layer 0/1 work earlier the same day). Lazily loaded,
once per process, matching the established pattern (:func:`core.analysis
.calculate_advanced_linguistic_metrics._get_embedder`, :func:`core.analysis.syntactic_complexity
._get_nlp`).

**Deliberately non-gating, unlike Layer 0/1.** This module computes and persists a real
contradiction score, but does *not* reject responses or affect ``v_ok`` -- CLAUDE.md SS3a's own
Layer 1 threshold only became trustworthy after being calibrated against real generated data (see
``docs/source/wiki/04-llm-analytics.rst``'s threshold-inversion finding), and no equivalent
real-data calibration exists yet for a contradiction-rejection threshold here. Shipping an
uncalibrated gate would repeat exactly the mistake that calibration process caught, just for a
different field. The model's own predicted label (argmax over contradiction/entailment/neutral) is
reported as a real, honest signal; turning it into a rejection gate is deferred, explicitly, to
the author's own future review of real RAG-enabled run data -- the same "collect real data first,
calibrate second" discipline Layer 1 already went through.
"""

from typing import Optional

import numpy as np
from sentence_transformers import CrossEncoder

_NLI_MODEL_NAME = "cross-encoder/nli-MiniLM2-L6-H768"
_LABELS = ("contradiction", "entailment", "neutral")
_nli_model: Optional[CrossEncoder] = None


def _get_nli_model() -> CrossEncoder:
    """Lazily construct (once per process) and return the shared NLI cross-encoder."""
    global _nli_model
    if _nli_model is None:
        _nli_model = CrossEncoder(_NLI_MODEL_NAME)
    return _nli_model


def check_hallucination(response_text: str, rag_context: str) -> dict:
    """
    Check whether ``response_text`` contradicts ``rag_context``.

    Parameters
    ----------
    response_text : str
        The generated response to check.
    rag_context : str
        The concatenated RAG-retrieved context the response was generated against (empty string
        when RAG is disabled for the run -- the same field :meth:`core.services.experiment_runner
        .ExperimentRunner._run_one` already builds and persists as ``rag_context``).

    Returns
    -------
    dict
        ``{"checked": bool, "predicted_label": str | None, "contradiction_score": float | None}``.
        ``checked`` is ``False`` (and the other two fields ``None``) whenever ``rag_context`` or
        ``response_text`` is empty/whitespace-only -- there is nothing to check consistency
        against. ``contradiction_score`` is a softmax probability in ``[0, 1]``, not a raw logit.
    """
    if not rag_context or not rag_context.strip() or not response_text or not response_text.strip():
        return {"checked": False, "predicted_label": None, "contradiction_score": None}

    model = _get_nli_model()
    logits = model.predict([(rag_context, response_text)])[0]
    probs = np.exp(logits) / np.exp(logits).sum()
    predicted_label = _LABELS[int(np.argmax(probs))]

    return {
        "checked": True,
        "predicted_label": predicted_label,
        "contradiction_score": round(float(probs[0]), 4),
    }
