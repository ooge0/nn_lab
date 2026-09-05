"""
core.domain.entities
=====================

Plain data entities passed between ``core.domain`` interfaces. Pydantic
models, matching the validated-entity convention already used elsewhere in
this codebase (``core.analysis.data_contract.LabSchema``,
``core.analysis.calculate_advanced_linguistic_metrics.LinguisticMetrics``) --
pydantic is a data-validation library, not a web framework, so it does not
violate the "zero framework imports" rule for this package (FastAPI itself
is built on it, which also makes these directly reusable as API DTOs later
without ``core.domain`` importing FastAPI).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PromptMode(str, Enum):
    """
    The three system-prompt construction modes the legacy app offers
    (``streamlit_app.py``, the ``prompt_strategy`` radio button). Values are
    the exact existing UI strings, so :class:`~core.adapters.prompt_strategy
    .NaivePromptStrategy` (Stage 3) can port the current behaviour without a
    remapping table.
    """

    TUNED = "Behavioral conditioning (Tuned)"
    BLIND = "Blind mode (Hide label)"
    RAW = "Raw / No system prompt"


class GenerationResult(BaseModel):
    """
    Raw output of one :meth:`~core.domain.interfaces.LLMClient.generate` call.

    Parameters
    ----------
    text : str
        The model's response content, exactly as returned (not yet parsed or
        classified -- malformed/truncated/empty detection is the judge
        layer's job, not the client's).
    duration_ms : float
        Wall-clock generation time in milliseconds, measured client-side
        (``time.time()`` around the call) -- always populated, regardless of
        backend.
    model : str
        The model name the request was sent to.
    prompt_tokens, completion_tokens : int, optional
        Real token counts, if the backend reports them (Ollama's native API
        does, via ``prompt_eval_count``/``eval_count``) -- ``None`` for a
        backend that doesn't. More accurate than any word-count-based proxy
        computed downstream from ``text``.
    ollama_total_duration_ms, ollama_load_duration_ms, ollama_prompt_eval_duration_ms, ollama_eval_duration_ms : float, optional
        Ollama's own self-reported timing breakdown (model-side, not the
        client wall-clock ``duration_ms`` above -- converted from Ollama's
        native nanosecond fields, not otherwise altered): total time,
        model-load time, prompt-evaluation time, and generation time
        respectively. ``None`` for any backend that isn't Ollama's native
        API (or a future non-Ollama backend). Enables real tokens/second
        (``completion_tokens`` / (``ollama_eval_duration_ms`` / 1000)) and a
        genuine load-time-vs-inference-time split, instead of the
        word-count/wall-clock proxy (``ms_per_word``) every backend can
        compute regardless of what it reports.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    duration_ms: float
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    ollama_total_duration_ms: Optional[float] = None
    ollama_load_duration_ms: Optional[float] = None
    ollama_prompt_eval_duration_ms: Optional[float] = None
    ollama_eval_duration_ms: Optional[float] = None


class JudgeVerdict(BaseModel):
    """
    Structured judge output -- the alternative to deciding pass/fail via
    string-matching raw judge text (CLAUDE.md SS1, SS4). ``confidence`` and
    ``rationale`` stay optional even though :class:`~core.adapters.structured_judge.StructuredJudge`
    (the author's explicit fix to the original naive, string-matching judge --
    see CLAUDE.md SS4/SS6) populates both when the judge model cooperates:
    a malformed/unparseable judge response still needs a valid
    ``JudgeVerdict`` with no real confidence/rationale to report, and any
    future ``Judge`` implementation isn't required to populate them either.

    Parameters
    ----------
    verdict : bool
        Pass (``True``) or fail (``False``).
    confidence : float, optional
        Judge's confidence in the verdict, if available.
    rationale : str, optional
        Free-text explanation for the verdict, if available.
    """

    verdict: bool
    confidence: Optional[float] = None
    rationale: Optional[str] = None


class ExperimentConfig(BaseModel):
    """
    One experiment run's configuration -- the same shape whether it comes
    from a web form (Stage 6) or a CLI config file (Stage 15), so
    ``ExperimentRunner`` has exactly one input type regardless of front end.

    Parameters
    ----------
    student_models : list[str]
        Models being evaluated (the "student" role).
    teacher_model : str, optional
        Judge/teacher model, required unless ``self_critic`` is set.
    self_critic : bool
        If ``True``, each student model judges its own output (known
        sycophancy risk -- CLAUDE.md SS4).
    archetypes : list[str]
        Behavioral archetype labels to generate against.
    biases : list[str]
        Bias descriptors injected into the prompt.
    prompt_mode : PromptMode
        Which of the three system-prompt construction strategies to use.
    exclude_archetype_from_prompt : bool
        Only meaningful in :attr:`PromptMode.TUNED` -- omits the literal
        archetype name from the generated prompt.
    rag_enabled : bool
        Whether to retrieve and inject knowledge-base context.
    rag_mode : str, optional
        Retrieval query strategy ("Archetype ONLY" / "Archetype + Bias" / bias
        only), required if ``rag_enabled``.
    rag_top_k : int, optional
        Number of chunks to retrieve, required if ``rag_enabled``.
    sweep_param : str, optional
        Which generation parameter (if any) is being swept across a value
        range for this run -- one of "Temperature"/"Top P"/"Frequency
        penalty"/"Presence penalty", or ``None`` for a single static value
        (the legacy app's "None" sweep option, which still counts as a
        one-point sweep at the relevant ``base_*`` value).
    sweep_min, sweep_max : float, optional
        The resolved value range to sweep across. Resolved server-side
        before this entity is constructed regardless of how the range was
        specified client-side (the legacy app's "Delta" mode -- center +/-
        delta -- vs "MIN-MAX" mode -- an explicit range -- both collapse to
        a concrete min/max here; the entity does not need to know which
        input mode produced them).
    sweep_steps : int
        Number of points to sample between ``sweep_min`` and ``sweep_max``
        (2-20 in the legacy UI; 1 is meaningless as a "sweep" but not
        rejected -- see :func:`core.services.experiment_runner
        .compute_sweep_range`).
    sweep_ascending : bool
        Sort direction for the computed value list. Only visibly matters
        for "Delta" mode in the legacy app (MIN-MAX is already ordered by
        construction) but is applied uniformly here.
    base_temperature, base_top_p, base_frequency_penalty, base_presence_penalty : float
        Generation parameter defaults, overridden by the swept value for
        whichever one ``sweep_param`` names.
    max_tokens : int, optional
        Generation token cap.
    seed : int, optional
        Generation seed, for reproducibility.
    """

    student_models: list[str]
    teacher_model: Optional[str] = None
    self_critic: bool = False
    archetypes: list[str]
    biases: list[str]
    prompt_mode: PromptMode
    exclude_archetype_from_prompt: bool = False
    rag_enabled: bool = False
    rag_mode: Optional[str] = None
    rag_top_k: Optional[int] = None
    sweep_param: Optional[str] = None
    sweep_min: Optional[float] = None
    sweep_max: Optional[float] = None
    sweep_steps: int = 1
    sweep_ascending: bool = True
    base_temperature: float = 0.7
    base_top_p: float = 0.9
    base_frequency_penalty: float = 0.0
    base_presence_penalty: float = 0.0
    max_tokens: Optional[int] = None
    seed: Optional[int] = None


class RunRecord(BaseModel):
    """
    Run-level metadata, stored **once per run** rather than repeated on every
    response row. Directly motivated by Stage 0's finding against real data:
    21.3% of every row's bytes in a sampled export were exactly-repeated
    run-level fields (``system_prompt``, ``archetype_about``, ``strategy``,
    ``total_tasks``) -- this entity is what a normalized
    :class:`~core.domain.interfaces.Repository` implementation (e.g.
    ``SQLiteRepo``, Stage 3) stores once and joins against, instead of
    re-serializing on every response.

    Parameters
    ----------
    run_id : str
        Unique identifier for this run.
    started_at : str
        ISO 8601 timestamp of when the run started.
    config : ExperimentConfig
        The configuration this run was started with.
    total_tasks : int
        Total number of response-generation tasks in this run.
    """

    run_id: str
    started_at: str
    config: ExperimentConfig
    total_tasks: int
