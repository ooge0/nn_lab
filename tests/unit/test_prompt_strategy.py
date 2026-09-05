"""
Unit tests for :class:`core.adapters.prompt_strategy.NaivePromptStrategy` --
pins exact expected output strings against a fixed archetypes fixture,
matching CLAUDE.md SS7 (don't assume ported logic is correct; pin outputs on
known inputs so a future change surfaces as a failing test).
"""

import pytest

from core.adapters.prompt_strategy import NaivePromptStrategy
from core.domain.entities import PromptMode

ARCHETYPES = {
    "common": {
        "intro": "Act as a system for behavioral conditioning.",
        "pre_phrase": "Apply behavioral constraints: ",
        "post_phrase_main": 'Respond ONLY as {"text": "<rewritten output>"}',
        "post_phrase_rules": "No filler, no markdown, no extra keys.",
    },
    "Detached": {
        "sys_prompt_main": "Enforce extreme emotional coldness and flat affect.",
        "about": "Detached archetype description.",
    },
}


@pytest.fixture
def strategy():
    return NaivePromptStrategy(ARCHETYPES)


def test_tuned_mode_includes_archetype_name(strategy):
    """TUNED mode names the archetype explicitly, matching streamlit_app.py lines 901-909."""
    result = strategy.build("Detached", "personalization, formal, toxic", PromptMode.TUNED)
    assert result == (
        "Act as a system for behavioral conditioning. "
        "Apply behavioral constraints: Detached archetype "
        "(bias: personalization, formal, toxic). "
        'Respond ONLY as {"text": "<rewritten output>"} '
        "No filler, no markdown, no extra keys."
    )


def test_tuned_mode_excludes_archetype_name_when_requested(strategy):
    """TUNED mode with exclude_archetype_from_prompt=True omits the archetype name entirely.

    Note the trailing double period in the expected string ("keys..") -- the
    legacy preview code (streamlit_app.py line 670) appends its own "."
    after post_phrase_rules regardless of whether the phrase already ends
    with one; ported here unchanged, not a typo.
    """
    result = strategy.build(
        "Detached", "personalization, formal, toxic", PromptMode.TUNED, exclude_archetype_from_prompt=True
    )
    assert "Detached" not in result
    assert result == (
        "Act as a system for behavioral conditioning. "
        "(bias: personalization, formal, toxic). "
        'Respond ONLY as {"text": "<rewritten output>"}.\n '
        "No filler, no markdown, no extra keys.."
    )


def test_blind_mode_hides_the_archetype_label(strategy):
    """BLIND mode never mentions the archetype name, matching streamlit_app.py lines 910-917."""
    result = strategy.build("Detached", "personalization, formal, toxic", PromptMode.BLIND)
    assert "Detached" not in result
    assert result == (
        "Act as a system for behavioral conditioning. "
        "Rewrite using personality traits. "
        "(bias: personalization, formal, toxic). "
        'Respond ONLY as {"text": "<rewritten output>"} '
        "No filler, no markdown, no extra keys."
    )


def test_raw_mode_uses_only_the_archetypes_own_sys_prompt(strategy):
    """RAW mode ignores the 'common' phrases entirely, matching streamlit_app.py lines 918-922."""
    result = strategy.build("Detached", "personalization, formal, toxic", PromptMode.RAW)
    assert result == "Enforce extreme emotional coldness and flat affect. (bias: personalization, formal, toxic)"


def test_unknown_mode_raises_value_error(strategy):
    """A mode outside the three known PromptMode members raises, rather than silently falling through."""
    with pytest.raises(ValueError):
        strategy.build("Detached", "bias", "not-a-real-mode")
