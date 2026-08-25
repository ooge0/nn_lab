"""
api.routers.experiments
==========================

Full ``tab_gen`` parity (Stage 6): every student model x archetype x bias
x swept-value combination, judged, optionally RAG-augmented, through the
real SSE + background-thread mechanism proven in Stage 1.
"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.adapters.ollama_client import OllamaClient
from core.adapters.structured_judge import StructuredJudge
from core.adapters.prompt_strategy import NaivePromptStrategy
from core.adapters.rag.knowledge_base import RAGKnowledgeBase
from core.domain.entities import ExperimentConfig, PromptMode
from core.services.experiment_runner import (
    ExperimentRunner,
    InvalidExperimentConfigError,
    RunProgressEvent,
    TooManyTasksError,
    compute_sweep_range,
)
from utils import config_loader_short
from utils.app_utils import AppUtils

router = APIRouter(prefix="/experiments", tags=["experiments"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_archetypes = AppUtils().load_archetypes(str(config_loader_short.SYS_PROMPTS_DEFINED_FILE_PATH))
_runner = ExperimentRunner(
    llm_client=(_ollama := OllamaClient()),
    repository=JSONLStore(),
    prompt_strategy=NaivePromptStrategy(_archetypes),
    judge=StructuredJudge(_ollama),
    archetypes=_archetypes,
    knowledge_base=None,  # set lazily on first RAG-enabled request, see _get_knowledge_base
    max_total_tasks=config_loader_short.MAX_TOTAL_TASKS,
)
_knowledge_base = None  # lazily built on first RAG-enabled request, see _get_knowledge_base


def _get_knowledge_base() -> RAGKnowledgeBase:
    """
    Lazily build and load the RAG knowledge base on first use.

    Notes
    -----
    ``RAGKnowledgeBase``'s underlying ``RAGEngine`` loads a
    ``SentenceTransformer`` model at construction time -- a real,
    multi-second cost. Not worth paying at import time (every app start,
    every test collection, every Sphinx build) for a feature that's
    optional per-request; paid once, lazily, only if a request actually
    enables RAG.

    The module-level ``_knowledge_base`` global is only assigned *after*
    ``load_knowledge_base`` succeeds -- assigning it first (as an earlier
    version of this function did) meant a failed load (e.g. an empty
    ``knowledge/rag/`` directory) permanently "poisoned" this cache: the
    ``is None`` check below would then be false forever, so every
    subsequent RAG-enabled request would silently reuse the same broken,
    never-loaded instance instead of ever retrying, even after the
    underlying problem was fixed without restarting the process.
    """
    global _knowledge_base
    if _knowledge_base is None:
        candidate = RAGKnowledgeBase()
        candidate.load_knowledge_base(str(config_loader_short.KNOWLEDGE_PATH))
        _knowledge_base = candidate
        _runner.set_knowledge_base(_knowledge_base)
    return _knowledge_base


def _bool(form, key: str) -> bool:
    """HTML checkboxes are present-with-any-value when checked, absent when not."""
    return key in form


def _float(form, key: str, default: float) -> float:
    value = form.get(key)
    return float(value) if value not in (None, "") else default


def _int_or_none(form, key: str) -> "int | None":
    value = form.get(key)
    return int(value) if value not in (None, "") else None


def _config_from_form(form) -> ExperimentConfig:
    """
    Build an ``ExperimentConfig`` from raw submitted form data, resolving
    the sweep "Delta"/"MIN-MAX" mode distinction to a concrete
    ``sweep_min``/``sweep_max`` range (the entity itself doesn't need to
    know which mode produced them -- see ``ExperimentConfig``'s docstring).
    """
    student_models = form.getlist("student_models")
    archetypes = form.getlist("archetypes")

    biases_raw = form.get("biases_raw", "")
    biases = [b.strip() for b in biases_raw.split(",") if b.strip()] if _bool(form, "split_biases") else [biases_raw]

    sweep_param = form.get("sweep_param") or None
    base_temperature = _float(form, "base_temperature", 0.7)
    base_top_p = _float(form, "base_top_p", 0.9)
    base_frequency_penalty = _float(form, "base_frequency_penalty", 0.0)
    base_presence_penalty = _float(form, "base_presence_penalty", 0.0)

    sweep_min = sweep_max = None
    sweep_ascending = True
    if sweep_param:
        center = {
            "Temperature": base_temperature,
            "Top P": base_top_p,
            "Frequency penalty": base_frequency_penalty,
            "Presence penalty": base_presence_penalty,
        }[sweep_param]
        if form.get("sweep_mode", "Delta") == "Delta":
            delta = _float(form, "sweep_delta", 0.2)
            sweep_min, sweep_max = center - delta, center + delta
            sweep_ascending = not _bool(form, "sweep_desc")
        else:  # MIN-MAX -- always ascending, matching the legacy UI's disabled ASC/DESC checkboxes
            sweep_min = _float(form, "sweep_min", center - 0.2)
            sweep_max = _float(form, "sweep_max", center + 0.2)
            sweep_ascending = True

    return ExperimentConfig(
        student_models=student_models,
        teacher_model=form.get("teacher_model") or None,
        self_critic=_bool(form, "self_critic"),
        archetypes=archetypes,
        biases=biases,
        prompt_mode=PromptMode(form.get("prompt_mode", PromptMode.TUNED.value)),
        exclude_archetype_from_prompt=_bool(form, "exclude_archetype_from_prompt"),
        rag_enabled=_bool(form, "rag_enabled"),
        rag_mode=form.get("rag_mode") or None,
        rag_top_k=_int_or_none(form, "rag_top_k"),
        sweep_param=sweep_param,
        sweep_min=sweep_min,
        sweep_max=sweep_max,
        sweep_steps=int(form.get("sweep_steps", 1) or 1),
        sweep_ascending=sweep_ascending,
        base_temperature=base_temperature,
        base_top_p=base_top_p,
        base_frequency_penalty=base_frequency_penalty,
        base_presence_penalty=base_presence_penalty,
        max_tokens=_int_or_none(form, "max_tokens"),
        seed=_int_or_none(form, "seed"),
    )


@router.get("", response_class=HTMLResponse)
async def experiments_page(request: Request) -> HTMLResponse:
    """
    Render the experiment page: full parity controls, plus an initial
    setup-summary preview matching the form's own hardcoded HTML defaults
    (so the preview panel shows something real from the first paint, not
    an empty/undefined placeholder -- the same context shape
    ``_experiment_preview.html`` needs whether it's rendered here or by
    ``POST /experiments/preview``).
    """
    archetype_names = [k for k in _archetypes.keys() if k != "common"]
    default_config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="qwen:latest",
        archetypes=[],  # matches the form's own default: nothing pre-selected, required to submit
        biases=["personalization, formal, toxic"],
        prompt_mode=PromptMode.TUNED,
        rag_mode="Archetype + Bias",
        base_temperature=0.7,
        base_top_p=0.9,
        max_tokens=512,
        seed=42,
    )
    return templates.TemplateResponse(
        request,
        "experiments.html",
        {
            "archetypes": archetype_names,
            "prompt_modes": list(PromptMode),
            "config": default_config,
            "total_tasks": ExperimentRunner.compute_total_tasks(default_config),
            "over_cap": False,
            "cap": _runner.max_total_tasks,
            "sweep_values": None,
        },
    )


@router.post("/preview", response_class=HTMLResponse)
async def experiments_preview(request: Request) -> HTMLResponse:
    """
    Return the live setup summary -- total task count plus a full recap of
    every selected value -- for the form's preview panel (no run started).

    Renders unconditionally on every field change (see the form's own
    ``hx-trigger``), so the author can see exactly what's about to run
    *before* clicking "Run experiment" -- previously this only showed the
    bare task count, not which models/archetypes/sweep range it actually
    resolved to, which made it easy to misread one experiment's results as
    another's after several form tweaks in a row.
    """
    form = await request.form()
    config = _config_from_form(form)
    total = ExperimentRunner.compute_total_tasks(config)
    over_cap = _runner.max_total_tasks is not None and total > _runner.max_total_tasks

    sweep_values = None
    if config.sweep_param and config.sweep_min is not None and config.sweep_max is not None:
        sweep_values = compute_sweep_range(
            config.sweep_min, config.sweep_max, config.sweep_steps, config.sweep_ascending
        )

    return templates.TemplateResponse(
        request,
        "_experiment_preview.html",
        {
            "total_tasks": total,
            "over_cap": over_cap,
            "cap": _runner.max_total_tasks,
            "config": config,
            "sweep_values": sweep_values,
        },
    )


@router.post("/start", response_class=HTMLResponse)
async def experiments_start(request: Request) -> HTMLResponse:
    """
    Start a full experiment and return the SSE-connecting fragment.

    Returns
    -------
    HTMLResponse
        202, with the ``hx-ext="sse"`` fragment, on success.
    HTMLResponse
        409, if a run is already in progress.
    HTMLResponse
        413, if the computed task count exceeds the configured cap
        (`TooManyTasksError`) -- refused before any generation starts.
    HTMLResponse
        400, if the submitted config is invalid for its own settings
        (`InvalidExperimentConfigError` -- e.g. a sweep with no resolved
        range, or no teacher model while self-critic is off), or if
        ``rag_enabled`` is set but the knowledge base can't actually be
        built (``RAGEngine.load_knowledge_base`` raises ``ValueError``/
        ``RuntimeError`` for an empty or unreadable ``knowledge/rag/``
        directory) -- refused before any generation starts, not a bare
        500 from an unhandled exception deep in the RAG adapter.
    """
    form = await request.form()
    config = _config_from_form(form)

    if config.rag_enabled:
        try:
            _get_knowledge_base()
        except (ValueError, RuntimeError) as exc:
            return templates.TemplateResponse(
                request,
                "_experiment_fragment.html",
                {"error": f"RAG knowledge base unavailable: {exc}"},
                status_code=400,
            )

    loop = asyncio.get_running_loop()
    try:
        queue = _runner.try_start(loop, config)
    except InvalidExperimentConfigError as exc:
        return templates.TemplateResponse(request, "_experiment_fragment.html", {"error": str(exc)}, status_code=400)
    except TooManyTasksError as exc:
        return templates.TemplateResponse(request, "_experiment_fragment.html", {"error": str(exc)}, status_code=413)

    if queue is None:
        return templates.TemplateResponse(
            request, "_experiment_fragment.html", {"error": "A run is already in progress."}, status_code=409
        )
    return templates.TemplateResponse(request, "_experiment_fragment.html", {"error": None}, status_code=202)


@router.post("/stop", response_class=HTMLResponse)
async def experiments_stop(request: Request) -> HTMLResponse:
    """
    Ask the in-progress run to halt after its current response finishes.

    See `ExperimentRunner.request_stop` -- cooperative, not preemptive: a
    generation call already in flight always completes and gets persisted
    first, so the actual stop lands on the *next* SSE ``progress`` event,
    not immediately on this response.

    Returns
    -------
    HTMLResponse
        200, with a short confirmation fragment, if a run was in progress
        and has been asked to stop.
    HTMLResponse
        409, with a short "nothing to stop" fragment, if no run was in
        progress.
    """
    stopped = _runner.request_stop()
    if not stopped:
        return templates.TemplateResponse(request, "_stop_fragment.html", {"stopped": False}, status_code=409)
    return templates.TemplateResponse(request, "_stop_fragment.html", {"stopped": True})


def _progress_fragment(item: RunProgressEvent) -> str:
    """
    Build one ``#experiment-progress`` SSE fragment -- a real HTML5
    ``<progress>`` bar (not just a text line, which is all this used to
    render -- a real gap, not a styling nicety: without it there is no
    visual indication a run is even moving).

    On the terminal ``done`` event, also renders direct links to the
    finished run's read-side pages -- previously the only way to see a
    result was to know to navigate to ``/runs`` (or ``/analytics``/``/nlp``/
    ``/clusters``) and manually pick the run from its dropdown; the pages
    all default to the most-recently-started run, so a bare link to each
    is correct without any query-param plumbing (this app is explicitly
    single-user, single-run-at-a-time -- see CLAUDE.md).

    While a run is in progress (``started``/``generating``), also renders a
    Stop button (``POST /experiments/stop``) -- restores the legacy
    sidebar's "Stop generation" button, dropped during the rewrite (see
    `ExperimentRunner.request_stop`). Omitted on every terminal stage
    (``done``/``stopped``/``error``), since there is nothing left to stop.
    """
    _stop_button = (
        '<button hx-post="/experiments/stop" hx-target="this" hx-swap="outerHTML" type="button">Stop</button>'
    )
    if item.stage == "error":
        return f'<div id="experiment-progress"><p class="error">Error: {item.error}</p></div>'
    if item.stage == "stopped":
        return (
            '<div id="experiment-progress">'
            f'<progress value="{item.step}" max="{item.total_tasks}"></progress> '
            f"<p>Stopped -- {item.step}/{item.total_tasks} completed before the stop request, run {item.run_id}.</p>"
            "<p>View partial results: "
            '<a href="/runs">Run summary</a> &middot; '
            '<a href="/analytics">Analytics</a> &middot; '
            '<a href="/nlp">Deep NLP</a> &middot; '
            '<a href="/clusters">Clusters</a></p>'
            "</div>"
        )
    if item.stage == "done":
        return (
            '<div id="experiment-progress">'
            f'<progress value="{item.step}" max="{item.total_tasks}"></progress> '
            f"<p>Done -- {item.step}/{item.total_tasks} -- run {item.run_id}</p>"
            "<p>View results: "
            '<a href="/runs">Run summary</a> &middot; '
            '<a href="/analytics">Analytics</a> &middot; '
            '<a href="/nlp">Deep NLP</a> &middot; '
            '<a href="/clusters">Clusters</a></p>'
            "</div>"
        )
    if item.step is not None:
        return (
            '<div id="experiment-progress">'
            f'<progress value="{item.step}" max="{item.total_tasks}"></progress> {item.step}/{item.total_tasks}&hellip; '
            f"{_stop_button}"
            "</div>"
        )
    return f'<div id="experiment-progress"><progress></progress> {item.stage}&hellip; {_stop_button}</div>'


@router.get("/stream", response_class=EventSourceResponse)
async def experiments_stream():
    """
    Stream progress for the current (or most recently started) run.

    Yields
    ------
    ServerSentEvent
        One ``progress`` event per response generated (``step``/``total_tasks``),
        followed by a ``progress-done`` event once the terminal event fires,
        so the client closes deliberately.
    """
    queue = _runner.queue
    if queue is None:
        yield ServerSentEvent(event="error", raw_data="No active run. POST /experiments/start first.")
        return

    while True:
        item = await queue.get()
        yield ServerSentEvent(event="progress", raw_data=_progress_fragment(item))
        if item.done:
            yield ServerSentEvent(event="progress-done", raw_data="")
            break
