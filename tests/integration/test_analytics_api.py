"""
Functional API tests for the Stage 8 read-side endpoints
(:mod:`api.routers.analytics`) -- through the real FastAPI app, with
``analytics._repository`` swapped for a fake so no real disk data is
required and no real Plotly-heavy computation is skipped (the charts are
built for real against fixture data, just not against a live-Ollama run).
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.analytics as analytics
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def _make_run(run_id, started_at, total_tasks=2):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


def _full_response(student, archetype, val, teacher="llama3:latest"):
    """A response record with every field every Stage 8 chart references."""
    return {
        "student": student,
        "teacher": teacher,
        "archetype": archetype,
        "val": val,
        "v_ok_numeric": 1,
        "duration_ms": 4000.0,
        "ms_per_word": 50.0,
        "word_count": 42,
        "unique_ratio": 0.7,
        "levenshtein_dist": 12,
        "semantic_overlap": 0.6,
        "punc_density": 0.1,
        "expansion_ratio": 1.1,
        "lexical_density": 0.5,
        "cognitive_load": 0.3,
        "zipf_deviation": 0.15,
        "prompt_tokens": 20,
        "completion_tokens": 8,
        "ollama_total_duration_ms": 100.0,
        "ollama_load_duration_ms": 5.0,
        "ollama_prompt_eval_duration_ms": 20.0,
        "ollama_eval_duration_ms": 40.0,
        "tokens_per_second": 200.0,
    }


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo = analytics._repository
    analytics._repository = fake_repo
    yield
    analytics._repository = original_repo


def test_analytics_page_with_no_runs_shows_empty_state(client):
    """GET /analytics with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/analytics")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_analytics_page_renders_all_three_subtabs_for_a_populated_run(client, fake_repo):
    """GET /analytics with a real run renders all three sub-tab headings and at least one chart div per sub-tab."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", _full_response("qwen:latest", "Detached", 0.2))
    fake_repo.save_response("run-a", _full_response("phi3:latest", "Anxious", 0.8))

    response = client.get("/analytics")
    assert response.status_code == 200
    assert "Adherence" in response.text
    assert "High-Dim analytics" in response.text
    assert "Zipf deviation" in response.text
    assert "Real generation speed" in response.text
    assert "plotly" in response.text.lower()


def test_analytics_charts_fragment_for_known_run_returns_populated_charts(client, fake_repo):
    """GET /analytics/charts?run_id=... for a run with responses returns real chart HTML, not the empty state."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-a", _full_response("qwen:latest", "Detached", 0.2))
    fake_repo.save_response("run-a", _full_response("phi3:latest", "Anxious", 0.8))

    response = client.get("/analytics/charts", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "No responses found" not in response.text
    assert "chart-" in response.text


def test_analytics_charts_fragment_for_unknown_run_returns_404_with_message(client):
    """GET /analytics/charts?run_id=... for a run with no persisted responses returns 404, matching /runs/summary's convention."""
    response = client.get("/analytics/charts", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_analytics_charts_does_not_500_on_a_sparse_pre_stage6_run(client, fake_repo):
    """
    Regression test for a real bug found on real disk data: an early
    (pre-Stage-6) export with only student/archetype/bias/duration_ms/output
    -- no teacher, no val, no metrics at all -- crashed the adherence
    sub-tab with a 500 because several charts assumed columns that simply
    weren't there. Must degrade gracefully instead (200, whatever charts
    the available columns support).
    """
    fake_repo.save_run(_make_run("run-sparse", "2026-08-21T00:00:00Z"))
    fake_repo.save_response(
        "run-sparse",
        {
            "student": "qwen:latest",
            "archetype": "Detached",
            "bias": "toxic",
            "duration_ms": 4000.0,
            "output": "some raw text",
        },
    )

    response = client.get("/analytics/charts", params={"run_id": "run-sparse"})
    assert response.status_code == 200
    assert "chart-" in response.text  # Latency and Workload distribution should still render


def test_analytics_charts_does_not_500_when_some_but_not_all_responses_lack_word_count(client, fake_repo):
    """
    Regression test for a real bug reproduced against a real 500-response live run: a Layer-0-
    rejected response (e.g. TRUNCATED) never gets word_count computed at all
    (ExperimentRunner._run_one skips metrics computation for it), so a run with even one such
    response alongside normal ones has a real, present-but-partially-NaN word_count column once
    loaded into a DataFrame. _add_if_present's column-existence check doesn't catch this -- most
    charts tolerate a NaN value, but the "Psycholinguistic signature" scatter uses word_count as
    Plotly marker `size`, whose validator rejects NaN outright and crashed the whole page with a
    real 500 (confirmed via a direct reproduction against live disk data, not assumed).
    """
    fake_repo.save_run(_make_run("run-mixed", "2026-08-21T00:00:00Z"))
    fake_repo.save_response("run-mixed", _full_response("qwen:latest", "Detached", 0.2))
    fake_repo.save_response("run-mixed", _full_response("qwen:latest", "Detached", 0.4))
    fake_repo.save_response(
        "run-mixed",
        {
            "student": "qwen:latest",
            "teacher": "llama3:latest",
            "archetype": "Detached",
            "val": 0.6,
            "v_ok_numeric": 0,
            "duration_ms": 1000.0,
            "layer0_classification": "TRUNCATED",
            # No word_count/punc_density/expansion_ratio at all -- matches a real Layer-0-rejected
            # entry, which never reaches metrics computation.
        },
    )

    response = client.get("/analytics/charts", params={"run_id": "run-mixed"})
    assert response.status_code == 200
    assert "Style distribution" in response.text  # the previously-crashing chart now renders


def test_analytics_charts_skips_high_dim_and_zipf_gracefully_when_columns_missing(client, fake_repo):
    """A run whose responses lack the high-dim/zipf columns renders the adherence charts but shows the graceful skip message for the others, not a 500."""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    fake_repo.save_response(
        "run-a",
        {
            "student": "qwen:latest",
            "teacher": "llama3:latest",
            "archetype": "Detached",
            "val": 0.2,
            "v_ok_numeric": 1,
            "duration_ms": 1000.0,
            "ms_per_word": 20.0,
            "word_count": 10,
            "unique_ratio": 0.5,
            "levenshtein_dist": 3,
            "semantic_overlap": 0.4,
            "punc_density": 0.05,
            "expansion_ratio": 1.0,
        },
    )

    response = client.get("/analytics/charts", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "skipped" in response.text
    assert "No Zipf deviation scores found" in response.text


def test_analytics_charts_include_prompt_strategy_charts_when_strategy_and_coherence_present(client, fake_repo):
    """Added 2026-08-24: 'strategy' was persisted on every response but never used as a chart
    grouping dimension anywhere -- these two charts answer 'does prompt structure affect stability.'"""
    fake_repo.save_run(_make_run("run-a", "2026-08-21T00:00:00Z"))
    base = _full_response("qwen:latest", "Detached", 0.2)
    tuned = {**base, "strategy": "Behavioral conditioning (Tuned)", "coherence": 0.8}
    blind = {**base, "strategy": "Blind", "coherence": 0.3}
    fake_repo.save_response("run-a", tuned)
    fake_repo.save_response("run-a", blind)

    response = client.get("/analytics/charts", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "Pass rate by prompt strategy" in response.text
    assert "Coherence stability by prompt strategy" in response.text
