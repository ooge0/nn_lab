"""
core.adapters.structured_judge
=================================

``Judge`` implementation that actually parses the structured JSON it asks the model for --
replacing :mod:`core.adapters.naive_judge`'s ``NaiveJudge``, which requested
``response_format={"type": "json_object"}`` but then decided pass/fail via
``"true" in content.lower()``, discarding the parsed structure entirely (CLAUDE.md SS4's
top-priority correctness gap, and the exact reason CLAUDE.md SS6 named this call site as the
author's own hand-written swap point rather than something built during the FastAPI rewrite).

This module is that swap, made by explicit author decision (not a default "AI-agent improves
whatever it finds" change) -- see CLAUDE.md SS4/SS6's updated text for the record of that decision,
and ``docs/source/wiki/04-llm-analytics.rst`` for the full before/after story, including the
Layer 0/Layer 1 gates (:mod:`core.analysis.response_classification`) that now run ahead of this
judge call in :meth:`core.services.experiment_runner.ExperimentRunner._run_one`.

Deliberately scoped: this fixes Layer 3 (the generative judge itself) to genuinely populate
``verdict``/``confidence``/``rationale``. It does not add Layer 2 (NLI/specialized classifiers) --
that remains unbuilt, disclosed as such in the wiki, not silently assumed to exist because this
file changed.
"""

import json
from typing import Optional

from core.domain.entities import JudgeVerdict
from core.domain.interfaces import LLMClient

_SYSTEM_PROMPT = (
    "You are evaluating whether a generated response matches the requested behavioral archetype "
    "and bias. Return JSON in exactly this shape, with no other text: "
    '{"verdict": true or false, "confidence": a number from 0.0 to 1.0, '
    '"rationale": "one short sentence explaining the verdict"}.'
)


class StructuredJudge:
    """
    ``Judge`` that genuinely parses the structured JSON verdict it requests from the model.

    Parameters
    ----------
    llm_client : LLMClient
        The client used to call the judge model.

    Notes
    -----
    A malformed, truncated, or non-JSON judge response is not silently treated as a genuine "no"
    the way :class:`~core.adapters.naive_judge.NaiveJudge` did -- it's reported as ``verdict=False,
    confidence=0.0`` with a ``rationale`` explaining *why* it's a fallback, not a real judgment. The
    fallback verdict is still ``False`` (a malformed response is not something to trust as a pass),
    but it's now distinguishable from a real "no" by reading ``rationale``, which
    :class:`~core.adapters.naive_judge.NaiveJudge` never even parsed far enough to produce.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def evaluate(self, response_text: str, archetype: str, bias: str, model: str) -> JudgeVerdict:
        """See :meth:`core.domain.interfaces.Judge.evaluate`."""
        user_prompt = f"Type: {archetype}\nBias: {bias}\nText: {response_text}"
        result = self._llm_client.generate(model, _SYSTEM_PROMPT, user_prompt, json_mode=True)
        return self._parse_verdict(result.text)

    @staticmethod
    def _parse_verdict(raw_text: str) -> JudgeVerdict:
        """
        Parse the judge model's raw response into a real ``JudgeVerdict``.

        Returns
        -------
        JudgeVerdict
            ``verdict``/``confidence``/``rationale`` from the parsed JSON on success.
            ``verdict=False, confidence=0.0`` with a ``rationale`` explaining the parse failure if
            the response isn't valid JSON, isn't a JSON object, or is missing the required
            ``"verdict"`` key -- a fallback state, not a claim the model genuinely said "no".
        """
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return JudgeVerdict(
                verdict=False, confidence=0.0, rationale=f"malformed judge response (not valid JSON): {exc}"
            )

        if not isinstance(parsed, dict) or "verdict" not in parsed:
            return JudgeVerdict(
                verdict=False, confidence=0.0, rationale="malformed judge response (missing 'verdict' key)"
            )

        verdict = bool(parsed["verdict"])

        confidence: Optional[float] = None
        raw_confidence = parsed.get("confidence")
        if raw_confidence is not None:
            try:
                confidence = max(0.0, min(1.0, float(raw_confidence)))
            except (TypeError, ValueError):
                confidence = None

        raw_rationale = parsed.get("rationale")
        rationale = str(raw_rationale) if raw_rationale is not None else None

        return JudgeVerdict(verdict=verdict, confidence=confidence, rationale=rationale)
