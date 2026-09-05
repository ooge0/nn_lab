"""
Unit tests for :mod:`utils.config_loader_short`'s dynamic ``__getattr__``
resolver -- specifically the ``[EXPERIMENT]`` section added for the Stage 6
total_tasks sanity cap, plus a regression check that the pre-existing
sections it resolves (used by the live legacy app and by
:mod:`core.adapters.ollama_client`/:mod:`core.adapters.jsonl_store`) are
still untouched.
"""

from utils import config_loader_short


def test_max_total_tasks_resolves_as_int():
    """[EXPERIMENT] max_total_tasks resolves via getint, not as a raw string."""
    assert isinstance(config_loader_short.MAX_TOTAL_TASKS, int)
    assert config_loader_short.MAX_TOTAL_TASKS > 0


def test_unknown_attribute_still_raises():
    """A name matching no section's keys still raises AttributeError, not silently returning None."""
    import pytest

    with pytest.raises(AttributeError):
        config_loader_short.NOT_A_REAL_CONFIG_KEY


def test_pre_existing_ollama_section_unaffected():
    """Adding the EXPERIMENT section didn't disturb the [OLLAMA] resolution OllamaClient depends on."""
    assert config_loader_short.OPENAI_BASE_URL == "http://localhost:11434/v1"
    assert config_loader_short.OPENAI_API_KEY == "ollama"


def test_pre_existing_directories_section_unaffected():
    """Adding the EXPERIMENT section didn't disturb the [DIRECTORIES] resolution JSONLStore depends on."""
    assert config_loader_short.RESULTS_DIR.name == "lab_experiment_results"
