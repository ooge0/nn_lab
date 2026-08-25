"""
Functional API tests for the Stage 11 read-side endpoints
(:mod:`api.routers.model_evo`) -- through the real FastAPI app, with
``model_evo._repository`` swapped for a fake so no real disk data is
required. :class:`~core.analysis.model_evaluation.ModelEvaluation` runs
for real against synthetic fixture data, not mocked out.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.routers.model_evo as model_evo
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


def _make_run(run_id, started_at, total_tasks=30):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached", "Expressive"],
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


def _classifiable_responses(n=30, seed=42):
    """
    30 synthetic responses split evenly across a 3-class ``archetype``
    label, with numeric features that actually correlate with the class
    (not pure noise) so LogisticRegression fits a real, non-degenerate
    model -- enough rows to clear ModelEvaluation's own ``< 10`` guard,
    and enough per-class members for ``train_test_split(..., stratify=y)``
    to succeed.
    """
    rng = np.random.default_rng(seed)
    archetypes = ["Detached", "Expressive", "Structured"]
    responses = []
    for i in range(n):
        archetype = archetypes[i % 3]
        offset = archetypes.index(archetype) * 2.0
        responses.append(
            {
                "student": "qwen:latest",
                "teacher": "llama3:latest",
                "archetype": archetype,
                "bias": "formal",
                "sentiment": float(rng.standard_normal() + offset),
                "rigidity": float(rng.standard_normal() + offset),
                "word_count": int(rng.integers(10, 100)),
            }
        )
    return responses


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repository(fake_repo):
    """Swap the module-level real JSONLStore for a fake-backed repository for the duration of each test."""
    original_repo = model_evo._repository
    model_evo._repository = fake_repo
    yield
    model_evo._repository = original_repo


def test_model_evo_page_with_no_runs_shows_empty_state(client):
    """GET /model_evo with zero persisted runs renders the empty-state message, not an error."""
    response = client.get("/model_evo")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_model_evo_targets_lists_discrete_columns_for_a_populated_run(client, fake_repo):
    """GET /model_evo/targets?run_id=... lists archetype/student/bias as candidate targets (2-10 unique values, non-float)."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z"))
    for r in _classifiable_responses():
        fake_repo.save_response("run-a", r)

    response = client.get("/model_evo/targets", params={"run_id": "run-a"})
    assert response.status_code == 200
    assert "archetype" in response.text
    assert "🚀 Run evaluation" in response.text


def test_model_evo_targets_for_unknown_run_returns_404_with_message(client):
    """GET /model_evo/targets?run_id=... for a run with no persisted responses returns 404, matching /nlp/charts's convention."""
    response = client.get("/model_evo/targets", params={"run_id": "never-started"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_model_evo_evaluate_renders_real_metrics_and_charts(client, fake_repo):
    """POST /model_evo/evaluate for a real classifiable dataset returns real precision/ROC-AUC numbers and chart HTML, not an error."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z"))
    for r in _classifiable_responses():
        fake_repo.save_response("run-a", r)

    response = client.post(
        "/model_evo/evaluate", data={"run_id": "run-a", "target_column": "archetype", "test_size": "0.2"}
    )
    assert response.status_code == 200
    assert "Evaluation failed" not in response.text
    assert "Precision" in response.text
    assert "Confusion matrix" in response.text
    assert "chart-" in response.text


def test_model_evo_evaluate_with_too_few_rows_renders_inline_error_not_500(client, fake_repo):
    """POST /model_evo/evaluate against a dataset under ModelEvaluation's own 10-row minimum shows an inline error, not a 500."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z", total_tasks=3))
    for r in _classifiable_responses(n=3):
        fake_repo.save_response("run-a", r)

    response = client.post(
        "/model_evo/evaluate", data={"run_id": "run-a", "target_column": "archetype", "test_size": "0.2"}
    )
    assert response.status_code == 200
    assert "Evaluation failed" in response.text
    assert "too small" in response.text


def test_model_evo_evaluate_with_missing_target_column_renders_inline_error(client, fake_repo):
    """POST /model_evo/evaluate with a target_column not present in the data shows an inline error, not a 500."""
    fake_repo.save_run(_make_run("run-a", "2026-08-22T00:00:00Z"))
    for r in _classifiable_responses():
        fake_repo.save_response("run-a", r)

    response = client.post(
        "/model_evo/evaluate", data={"run_id": "run-a", "target_column": "does_not_exist", "test_size": "0.2"}
    )
    assert response.status_code == 200
    assert "Evaluation failed" in response.text
    assert "not found" in response.text


def test_model_evo_evaluate_for_unknown_run_returns_404(client):
    """POST /model_evo/evaluate for a run with no persisted responses returns 404."""
    response = client.post(
        "/model_evo/evaluate", data={"run_id": "never-started", "target_column": "archetype", "test_size": "0.2"}
    )
    assert response.status_code == 404
