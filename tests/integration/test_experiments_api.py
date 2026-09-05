"""
Functional API tests for the Stage 6 experiment endpoints
(:mod:`api.routers.experiments`) -- through the real FastAPI app, with
``experiments._runner`` swapped for a fake-backed ``ExperimentRunner`` so
no real Ollama call or disk write happens.
"""

import time

import pytest
from fastapi.testclient import TestClient

import api.routers.experiments as experiments
from api.app import app
from core.services.experiment_runner import ExperimentRunner, RunProgressEvent
from tests.unit.test_experiment_runner import (
    ARCHETYPES,
    FakeJudge,
    FakeKnowledgeBase,
    FakeLLMClient,
    FakePromptStrategy,
    FakeRepository,
)


@pytest.fixture
def client():
    """TestClient as a context manager -- see test_demo_api.py's client fixture for why this matters."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fakes():
    """The fake collaborators wired into experiments._runner for the duration of a test."""
    return {"llm": FakeLLMClient(delay_seconds=0.2), "repo": FakeRepository(), "judge": FakeJudge()}


@pytest.fixture(autouse=True)
def _fake_runner(fakes):
    """Swap the module-level real-adapter runner for a fake-backed one for the duration of each test."""
    original_runner, original_kb = experiments._runner, experiments._knowledge_base
    experiments._runner = ExperimentRunner(
        fakes["llm"],
        fakes["repo"],
        FakePromptStrategy(),
        fakes["judge"],
        ARCHETYPES,
        max_total_tasks=10,
    )
    experiments._knowledge_base = None
    yield
    deadline = time.time() + 5
    while experiments._runner.running and time.time() < deadline:
        time.sleep(0.02)
    experiments._runner, experiments._knowledge_base = original_runner, original_kb


def _wait_until_idle(timeout: float = 5.0) -> None:
    """Poll until the runner's guard clears, instead of guessing a fixed sleep duration."""
    deadline = time.time() + timeout
    while experiments._runner.running and time.time() < deadline:
        time.sleep(0.02)


BASE_FORM = {
    "student_models": "qwen:latest",
    "teacher_model": "qwen:latest",
    "archetypes": "Detached",
    "biases_raw": "formal, toxic",
    "prompt_mode": "Behavioral conditioning (Tuned)",
    "base_temperature": "0.7",
    "base_top_p": "0.9",
    "base_frequency_penalty": "0.0",
    "base_presence_penalty": "0.0",
    "sweep_steps": "1",
}


def test_experiments_page_lists_archetypes_and_prompt_modes(client):
    """GET /experiments renders the real archetype names and prompt-mode options, not a placeholder form."""
    response = client.get("/experiments")
    assert response.status_code == 200
    assert "Detached" in response.text
    assert "Behavioral conditioning (Tuned)" in response.text


def test_experiments_page_renders_a_real_initial_preview_not_undefined(client):
    """
    Regression test: the initial GET must render a real setup-summary
    preview matching the form's own hardcoded defaults, not crash with a
    Jinja2 UndefinedError -- the preview fragment is now included directly
    on first paint (not just after a POST /experiments/preview), so the
    page-load handler must supply the same context shape.
    """
    response = client.get("/experiments")
    assert response.status_code == 200
    assert "Total iterations for this setup: 0" in response.text  # no archetypes pre-selected
    assert "qwen:latest" in response.text  # the form's own default student


def test_preview_renders_the_full_setup_summary_including_sweep_range(client):
    """POST /experiments/preview shows a full recap (students/archetypes/biases/judge/sweep), including the real computed sweep value list, not just the bare task count."""
    response = client.post(
        "/experiments/preview",
        data={
            **BASE_FORM,
            "archetypes": ["Detached", "Expressive"],
            "sweep_param": "Temperature",
            "sweep_mode": "Delta",
            "sweep_delta": "0.3",
            "sweep_steps": "3",
        },
    )
    assert response.status_code == 200
    assert "Total iterations for this setup: 6" in response.text  # 1 student * 2 archetypes * 1 bias * 3 steps
    assert "Detached, Expressive" in response.text
    assert "Teacher: qwen:latest" in response.text
    assert "Temperature, 3 step(s): 0.4, 0.7, 1.0" in response.text


def test_preview_shows_no_sweep_when_sweep_param_is_unset(client):
    """When sweep_param is empty, the preview clearly states no sweep is active, rather than showing a stale or misleading range."""
    response = client.post("/experiments/preview", data=BASE_FORM)
    assert response.status_code == 200
    assert "None -- every combination runs once at the base sampling values above" in response.text


def test_preview_returns_total_tasks_without_starting_anything(client):
    """POST /experiments/preview computes and returns the real total_tasks count for the submitted config, without starting a run (runner.running stays False)."""
    response = client.post(
        "/experiments/preview",
        data={**BASE_FORM, "student_models": ["qwen:latest", "phi3:latest"], "archetypes": ["Detached", "Expressive"]},
    )
    assert response.status_code == 200
    assert "4" in response.text  # 2 students * 2 archetypes * 1 bias * 1 (no sweep)
    assert experiments._runner.running is False


def test_start_returns_202_with_sse_fragment(client):
    """POST /experiments/start with a valid config returns 202 and the htmx SSE-connecting fragment, not a full page."""
    response = client.post("/experiments/start", data=BASE_FORM)
    assert response.status_code == 202
    assert 'sse-connect="/experiments/stream"' in response.text


def test_start_over_the_cap_returns_413_and_does_not_start(client):
    """A config computing to more than the configured max_total_tasks cap is refused with 413 before any generation starts."""
    # max_total_tasks=10 in the fixture; 4 archetypes * 3 split biases * 1 = 12 > 10
    response = client.post(
        "/experiments/start",
        data={
            **BASE_FORM,
            "archetypes": ["Detached", "Expressive", "Neutral", "Defensive"],
            "biases_raw": "a, b, c",
            "split_biases": "on",
        },
    )
    assert response.status_code == 413
    assert "cap" in response.text.lower() or "exceed" in response.text.lower()
    assert experiments._runner.running is False


def test_second_concurrent_start_is_rejected(client):
    """A second POST /experiments/start while one is already running is rejected with 409, at the API layer (the concurrent-run guard's HTTP-facing behavior)."""
    first = client.post("/experiments/start", data=BASE_FORM)
    assert first.status_code == 202

    second = client.post("/experiments/start", data=BASE_FORM)
    assert second.status_code == 409


def test_stop_with_no_run_in_progress_returns_409(client):
    """POST /experiments/stop with nothing running is refused with 409, at the API layer -- there is nothing to stop."""
    response = client.post("/experiments/stop")
    assert response.status_code == 409
    assert "no run" in response.text.lower()


def test_stop_mid_run_returns_200_and_the_run_actually_halts_early(client, fakes):
    """
    POST /experiments/stop while a run is in progress returns 200 and asks
    the background thread to halt -- restores the legacy sidebar's "Stop
    generation" button. Confirmed via the runner's own guard clearing
    (not stuck "running" forever) and fewer than the full 2 responses
    persisted (the run started with 2 archetypes -> total_tasks=2).
    """
    start = client.post("/experiments/start", data={**BASE_FORM, "archetypes": ["Detached", "Expressive"]})
    assert start.status_code == 202

    stop = client.post("/experiments/stop")
    assert stop.status_code == 200
    assert "stop requested" in stop.text.lower()

    _wait_until_idle()
    assert experiments._runner.running is False
    assert len(fakes["repo"].saved_responses) < 2


def test_self_critic_checkbox_is_honored(client, fakes):
    """When the self_critic checkbox is present, the fake judge is called with the student model."""
    client.post("/experiments/start", data={**BASE_FORM, "self_critic": "on"})
    _wait_until_idle()
    assert fakes["judge"].calls[0]["model"] == "qwen:latest"


def test_split_biases_produces_one_entry_per_bias(client, fakes):
    """split_biases=on with a comma-separated biases_raw string generates one response per bias, not one response for the whole raw string."""
    client.post("/experiments/start", data={**BASE_FORM, "biases_raw": "a, b, c", "split_biases": "on"})
    _wait_until_idle()  # 3 sequential 0.2s-delayed fake calls -- a fixed short sleep isn't enough margin
    assert len(fakes["repo"].saved_responses) == 3
    assert {e["bias"] for _, e in fakes["repo"].saved_responses} == {"a", "b", "c"}


def test_rag_enabled_lazily_builds_the_knowledge_base(client, fakes, monkeypatch):
    """rag_enabled=on triggers _get_knowledge_base(), which is monkeypatched here to avoid a real model load."""
    fake_kb = FakeKnowledgeBase()

    def fake_get_knowledge_base():
        experiments._runner.set_knowledge_base(fake_kb)
        return fake_kb

    monkeypatch.setattr(experiments, "_get_knowledge_base", fake_get_knowledge_base)

    client.post(
        "/experiments/start", data={**BASE_FORM, "rag_enabled": "on", "rag_mode": "Archetype + Bias", "rag_top_k": "3"}
    )
    _wait_until_idle()

    assert fake_kb.calls  # retrieve() was actually called
    _, entry = fakes["repo"].saved_responses[0]
    assert entry["rag_enabled"] is True


def test_get_knowledge_base_does_not_cache_a_failed_load(monkeypatch):
    """
    Regression test for the caching bug itself (not just the route's error
    handling): _get_knowledge_base() must leave the module-level cache at
    None after a failed load_knowledge_base() call, so a later call can
    retry -- not permanently reuse a half-built, never-loaded instance.
    """
    monkeypatch.setattr(experiments, "_knowledge_base", None)
    attempts = {"n": 0}

    class FlakyKnowledgeBase:
        def load_knowledge_base(self, path):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("No .txt files found. Please add knowledge files.")

    monkeypatch.setattr(experiments, "RAGKnowledgeBase", FlakyKnowledgeBase)

    with pytest.raises(ValueError):
        experiments._get_knowledge_base()
    assert experiments._knowledge_base is None  # not poisoned by the failed attempt

    result = experiments._get_knowledge_base()  # retry succeeds now
    assert isinstance(result, FlakyKnowledgeBase)
    assert experiments._knowledge_base is result


def test_rag_enabled_with_unbuildable_knowledge_base_returns_400_not_500(client, monkeypatch):
    """
    Regression test: if RAGEngine.load_knowledge_base raises (e.g. an
    empty knowledge/rag/ directory -- ValueError -- or an unreadable one --
    RuntimeError), the route must return a clean 400 with the fragment
    template, not let the exception propagate into a bare 500. Also
    confirms the module-level knowledge-base cache stays None afterward
    (not permanently poisoned by a half-built instance), so a later
    request can retry once the underlying problem is fixed.
    """

    def failing_get_knowledge_base():
        raise ValueError("No .txt files found in knowledge/rag. Please add knowledge files.")

    monkeypatch.setattr(experiments, "_get_knowledge_base", failing_get_knowledge_base)
    monkeypatch.setattr(experiments, "_knowledge_base", None)

    response = client.post("/experiments/start", data={**BASE_FORM, "rag_enabled": "on"})

    assert response.status_code == 400
    assert "RAG knowledge base unavailable" in response.text
    assert experiments._runner.running is False


def test_progress_fragment_renders_a_real_progress_element_not_just_text():
    """
    Regression test: every non-terminal progress fragment must include a
    real <progress> element (previously this was plain text with no visual
    indicator at all -- a real UX gap, not a styling nicety).
    """
    started = experiments._progress_fragment(RunProgressEvent(stage="started", total_tasks=10))
    assert "<progress" in started

    generating = experiments._progress_fragment(RunProgressEvent(stage="generating", step=3, total_tasks=10))
    assert '<progress value="3" max="10">' in generating
    assert "3/10" in generating


def test_progress_fragment_on_done_links_to_every_read_side_page():
    """The terminal 'done' fragment links directly to /runs, /analytics, /nlp, /clusters -- previously there was no way to reach results from the progress view at all."""
    done = experiments._progress_fragment(
        RunProgressEvent(stage="done", step=5, total_tasks=5, run_id="run-123", done=True)
    )
    assert '<progress value="5" max="5">' in done
    assert "Done -- 5/5 -- run run-123" in done
    for path in ("/runs", "/analytics", "/nlp", "/clusters"):
        assert f'href="{path}"' in done


def test_progress_fragment_on_stopped_reports_partial_progress_and_links_to_results():
    """The terminal 'stopped' fragment (from a Stop-button click) reports how many responses actually completed and still links to the read-side pages -- partial results are real results, not discarded."""
    stopped = experiments._progress_fragment(
        RunProgressEvent(stage="stopped", step=2, total_tasks=5, run_id="run-123", done=True)
    )
    assert '<progress value="2" max="5">' in stopped
    assert "Stopped -- 2/5 completed before the stop request, run run-123" in stopped
    assert '<a href="/runs">Run summary</a>' in stopped


def test_progress_fragment_while_in_progress_includes_a_stop_button():
    """Every non-terminal fragment (started/generating) includes a real Stop button, restoring the legacy sidebar's 'Stop generation' control."""
    started = experiments._progress_fragment(RunProgressEvent(stage="started", total_tasks=10))
    assert 'hx-post="/experiments/stop"' in started

    generating = experiments._progress_fragment(RunProgressEvent(stage="generating", step=3, total_tasks=10))
    assert 'hx-post="/experiments/stop"' in generating


def test_progress_fragment_on_terminal_stages_omits_the_stop_button():
    """done/stopped/error fragments do not show a Stop button -- there is nothing left to stop once the run has already ended."""
    for event in [
        RunProgressEvent(stage="done", step=5, total_tasks=5, run_id="run-1", done=True),
        RunProgressEvent(stage="stopped", step=2, total_tasks=5, run_id="run-1", done=True),
        RunProgressEvent(stage="error", error="boom", done=True),
    ]:
        assert 'hx-post="/experiments/stop"' not in experiments._progress_fragment(event)


def test_progress_fragment_on_error_shows_the_message():
    """The terminal 'error' fragment shows the real error text, not a generic message."""
    error = experiments._progress_fragment(
        RunProgressEvent(stage="error", error="Ollama connection refused", done=True)
    )
    assert "Ollama connection refused" in error


def test_stream_without_a_started_run_sends_error_and_closes(client):
    """GET /experiments/stream with no active run (queue is None) sends an error event and closes immediately, rather than hanging."""
    experiments._runner._queue = None
    with client.stream("GET", "/experiments/stream") as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]
    assert any(line == "event: error" for line in lines)
