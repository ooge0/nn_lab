"""
core.adapters.prompt_strategy
================================

``PromptStrategy`` implementation porting the exact three-mode system-prompt
construction from ``streamlit_app.py`` lines 901-930 (the per-iteration
prompt, not the multi-archetype preview at lines 664-692, which concatenates
several archetypes together for display and is not what actually gets sent
to the model).
"""

from core.domain.entities import PromptMode


class NaivePromptStrategy:
    """
    Ports the legacy three-mode prompt construction, unchanged.

    Parameters
    ----------
    archetypes : dict
        The archetypes definition (``knowledge/sys_prompts_defined.json``,
        loaded via ``utils.app_utils.AppUtils.load_archetypes``): a
        ``"common"`` key with ``intro``/``pre_phrase``/``post_phrase_main``/
        ``post_phrase_rules`` strings, plus one key per archetype with a
        ``sys_prompt_main`` string.

    Notes
    -----
    The legacy code has a fourth, unreachable ``else`` branch (lines
    923-930) for an unrecognized ``prompt_strategy`` value -- unreachable
    because the UI only ever offers the three known strings. Now that
    ``mode`` is a :class:`~core.domain.entities.PromptMode` enum with
    exactly three members, that branch is structurally impossible and is
    not ported; an unrecognized mode raises ``ValueError`` instead of
    silently falling through to dead-code behaviour nobody intentionally
    triggers.

    A genuine bug found while porting, deliberately **not** carried
    forward: the legacy "Exclude archetype from prompt" checkbox
    (``exclude_from_prompt``) only affects the UI *preview* text
    (``streamlit_app.py`` lines 654-671) -- it is never read in the real
    per-iteration generation code (lines 901-930) that builds what
    actually gets sent to the model. The checkbox visibly changes the
    preview but has zero effect on a real run. This adapter's
    ``exclude_archetype_from_prompt`` parameter implements the checkbox's
    evident intent (matching the preview's own behaviour) rather than
    silently cloning the no-op, since porting a bug forward just because
    "that's what the old app did" isn't the goal here.
    """

    def __init__(self, archetypes: dict) -> None:
        self._archetypes = archetypes

    def build(
        self,
        archetype: str,
        bias: str,
        mode: PromptMode,
        *,
        exclude_archetype_from_prompt: bool = False,
    ) -> str:
        """See :meth:`core.domain.interfaces.PromptStrategy.build`."""
        common = self._archetypes["common"]

        if mode == PromptMode.TUNED:
            if exclude_archetype_from_prompt:
                return (
                    f"{common['intro']} "
                    f"(bias: {bias}). "
                    f"{common['post_phrase_main']}.\n "
                    f"{common['post_phrase_rules']}."
                )
            return (
                f"{common['intro']} "
                f"{common['pre_phrase']}"
                f"{archetype} archetype "
                f"(bias: {bias}). "
                f"{common['post_phrase_main']} "
                f"{common['post_phrase_rules']}"
            )

        if mode == PromptMode.BLIND:
            return (
                f"{common['intro']} "
                "Rewrite using personality traits. "
                f"(bias: {bias}). "
                f"{common['post_phrase_main']} "
                f"{common['post_phrase_rules']}"
            )

        if mode == PromptMode.RAW:
            return f"{self._archetypes[archetype]['sys_prompt_main']} (bias: {bias})"

        raise ValueError(f"Unknown prompt mode: {mode!r}")
