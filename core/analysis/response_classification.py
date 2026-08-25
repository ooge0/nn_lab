"""
response_classification.py

Layer 0 and Layer 1 of the per-response evaluation cascade (CLAUDE.md SS3a). Both are
deterministic, static checks -- no LLM call, no orchestrator deciding what to do next, matching
CLAUDE.md SS3a's explicit "routing must be as reproducible as the tools it routes" requirement.

Layer 0 (``classify_response``) is a pure, model-free classification of the *raw* model response,
run before any metric computation touches it -- CLAUDE.md SS1's malformed-output taxonomy, scoped
to the four classes that are actually distinguishable without a second model call: ``VALID``,
``EMPTY``, ``MALFORMED_JSON``, ``TRUNCATED``, ``SCHEMA_ERROR``. (``API_ERROR`` isn't classified
here -- a real transport/API failure during generation already surfaces as an exception in
:meth:`core.services.experiment_runner.ExperimentRunner._run`, before a response ever reaches this
function; ``FORMAT_ERROR`` isn't distinguishable from the others by a purely syntactic check and
isn't attempted.)

Layer 1 (``is_echo_response``) flags a specific, real, previously-undetected failure mode: the
model echoing its own archetype/bias instruction back instead of generating conditioned text (a
real pattern this project's own data confirmed, not a hypothetical -- CLAUDE.md SS0's "empirically
confirmed judge gap" finding, 7/125 real outputs). It reuses the sentence-embedding similarity
:mod:`core.analysis.calculate_advanced_linguistic_metrics` already computes as ``semantic_overlap``
-- no second model call, no extra dependency -- rather than STS embeddings on a separate topical
signal. This is a narrow, verified slice of what CLAUDE.md SS3a calls "Layer 1: STS embeddings",
not the full topical-proximity gate that name implies; see docs/source/wiki/04-llm-analytics.rst
for what a broader Layer 1 (and the still entirely unbuilt Layer 2, NLI/specialized classifiers)
would still need.
"""

import json
from enum import Enum


class ResponseClassification(str, Enum):
    """Layer 0's possible outcomes -- a subset of CLAUDE.md SS1's seven-class taxonomy, see this module's own docstring for which three are out of scope here and why."""

    VALID = "VALID"
    EMPTY = "EMPTY"
    MALFORMED_JSON = "MALFORMED_JSON"
    TRUNCATED = "TRUNCATED"
    SCHEMA_ERROR = "SCHEMA_ERROR"


def classify_response(raw_text: str) -> ResponseClassification:
    """
    Layer 0: classify a raw model response before any metric computation or judge call touches it.

    Parameters
    ----------
    raw_text : str
        The model's raw response text, *before* :func:`core.services.experiment_runner.extract_best_text`
        -- this checks what the model actually returned, not the best-effort text extracted from it.

    Returns
    -------
    ResponseClassification
        ``EMPTY`` if the text is empty/whitespace-only, or if it parses as JSON with an empty
        ``"text"`` value. ``MALFORMED_JSON``/``TRUNCATED`` if the text isn't valid JSON --
        distinguished by a simple heuristic (unbalanced braces/quotes, or not ending on a sentence-
        or structure-closing character, suggests the response was cut off mid-generation rather
        than genuinely malformed from the start). ``SCHEMA_ERROR`` if it's valid JSON but not the
        expected ``{"text": "..."}`` shape. ``VALID`` otherwise.
    """
    if not raw_text or not raw_text.strip():
        return ResponseClassification.EMPTY

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        stripped = raw_text.rstrip()
        looks_cut_off = (
            raw_text.count("{") != raw_text.count("}")
            or raw_text.count('"') % 2 != 0
            or (bool(stripped) and stripped[-1] not in ".!?\"'}])")
        )
        return ResponseClassification.TRUNCATED if looks_cut_off else ResponseClassification.MALFORMED_JSON

    if not isinstance(parsed, dict) or "text" not in parsed:
        return ResponseClassification.SCHEMA_ERROR
    if not str(parsed.get("text", "")).strip():
        return ResponseClassification.EMPTY
    return ResponseClassification.VALID


# --- How this threshold and its direction were actually found (not guessed) ------------------
#
# The first design attempt assumed the standard STS intuition: LOW similarity to the prompt means
# off-topic, so reject low scores. Calibrating against real generated data
# (results/lab_experiment_results/*.jsonl -- real Ollama output, not synthetic examples) showed
# this was backwards for this specific task:
#
#   genuine, substantive archetype-conditioned responses:  semantic_overlap 0.06-0.30
#   confirmed echo failures (model repeats its own bias/instruction back, CLAUDE.md SS0's
#   real-data finding of 7/125 such cases):                semantic_overlap 0.59-0.98
#
# Cause: this project's "bias" field is not a natural-language prompt to be answered or closely
# paraphrased -- it's a short, comma-separated list of style/tone TAGS ("personalization, formal,
# toxic"), closer to categorical labels than to prose. A sentence-embedding model reads a long,
# substantive, on-topic response as naturally DISTANT from that terse tag string in embedding
# space (different length, different structure, different content entirely -- the response is
# *about* the tags, not a rewording of them). Echoing collapses that distance to near-zero because
# the echo *is*, almost verbatim, the tag string. The standard "low similarity = off-topic"
# intuition holds for prompt/answer pairs where a good answer stays close to the question; it does
# not hold here, where the "prompt" is a label, not a question. This is a concrete, verified
# example of testing surfacing the opposite conclusion from the naive first assumption -- exactly
# the discipline CLAUDE.md's "measurement validity" framing calls for, not a hypothetical.
#
# Open question, explicitly not resolved here: whether *other* properties of the bias field's
# content -- style/register, emotional valence, lexical rarity, or other neurolinguistic
# dimensions the archetype-conditioning design leans on -- would benefit from their own dedicated
# validation, is a genuinely open question this project has not investigated. The tag-like
# structure found here is one concrete data point, not a general theory of what "bias" is or
# should be. Flagged honestly as unexplored territory (see
# docs/source/wiki/04-llm-analytics.rst's own note on this) rather than guessed at.
#
# 0.5 sits in the wide, clean gap between the two observed clusters above.
_ECHO_SIMILARITY_THRESHOLD = 0.5


def is_echo_response(semantic_overlap: float) -> bool:
    """
    Layer 1: flag a response as a likely echo of its own bias/archetype instruction.

    Parameters
    ----------
    semantic_overlap : float
        The already-computed embedding-similarity value between the bias/archetype instruction
        and the response
        (:func:`core.analysis.calculate_advanced_linguistic_metrics.calculate_advanced_linguistic_metrics`'s
        ``semantic_overlap`` field) -- reused here, not recomputed, so this check costs nothing
        beyond the metric computation that already happens for every response.

    Returns
    -------
    bool
        ``True`` if ``semantic_overlap`` exceeds the calibrated threshold (see module-level
        constant above for the real data this was calibrated against).
    """
    return semantic_overlap > _ECHO_SIMILARITY_THRESHOLD
