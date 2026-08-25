"""
core.domain.interfaces
========================

The four interfaces every other layer depends on:
:class:`LLMClient`, :class:`Judge`, :class:`PromptStrategy`,
:class:`Repository` (plus :class:`KnowledgeBase` for RAG, kept separate
per the project's refactor plan rather than folded into ``Repository``).

Defined as ``typing.Protocol`` classes (structural typing -- an
implementation satisfies an interface by having matching methods, with no
inheritance required) marked ``@runtime_checkable`` so ``isinstance()``
conformance checks work in tests. Zero framework imports: nothing here may
import Streamlit, FastAPI, the OpenAI SDK, or the Ollama client --
``core.adapters`` implements these against those libraries; this module
must never import ``core.adapters``.
"""

from typing import Optional, Protocol, runtime_checkable

from core.domain.entities import GenerationResult, JudgeVerdict, PromptMode, RunRecord


@runtime_checkable
class LLMClient(Protocol):
    """
    A chat-completion client for one LLM backend (local Ollama, real OpenAI,
    or any other OpenAI-compatible endpoint).

    Shaped by the existing call in ``streamlit_app.py`` (the generation call
    at lines 953-961, and the identically-shaped judge call at lines
    982-994): both are a system prompt + a user prompt, a handful of
    sampling parameters, and an optional JSON-mode flag.
    """

    def generate(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        top_p: float = 0.9,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        max_tokens: Optional[int] = None,
        seed: Optional[int] = None,
        json_mode: bool = False,
    ) -> GenerationResult:
        """
        Generate one chat completion.

        Parameters
        ----------
        model : str
            Model name to call.
        system_prompt : str
            System-role message content.
        user_prompt : str
            User-role message content.
        temperature, top_p, frequency_penalty, presence_penalty : float, optional
            Sampling parameters.
        max_tokens : int, optional
            Generation token cap.
        seed : int, optional
            Generation seed, for reproducibility.
        json_mode : bool, optional
            If ``True``, requests a JSON-object response
            (``response_format={"type": "json_object"}``).

        Returns
        -------
        GenerationResult
            The raw response text and generation duration.

        Raises
        ------
        Exception
            Implementations propagate the underlying client's errors as-is
            (API errors, timeouts, ...) rather than swallowing them --
            classifying failures (``API_ERROR`` vs ``MALFORMED_JSON`` vs
            ...) is the judge/cascade layer's responsibility, not this
            interface's.
        """
        ...


@runtime_checkable
class Judge(Protocol):
    """
    Decides pass/fail for one generated response.

    Shaped by the existing validator call in ``streamlit_app.py`` lines
    982-996: a text to evaluate, plus the archetype and bias it was
    supposed to satisfy. Stage 4 wired this interface to that call's *exact*
    original (buggy) behaviour unchanged, as an explicit author-swap
    boundary; :class:`~core.adapters.structured_judge.StructuredJudge` is
    that swap, made by the author's own explicit decision (CLAUDE.md
    SS4/SS6) to fix the judge's structured-output parsing. Layer 2
    (NLI/specialized classifiers, CLAUDE.md SS3a) remains unbuilt -- this
    interface doesn't need to change if that lands later either.
    """

    def evaluate(self, response_text: str, archetype: str, bias: str, model: str) -> JudgeVerdict:
        """
        Evaluate whether ``response_text`` satisfies ``archetype``/``bias``.

        Parameters
        ----------
        response_text : str
            The generated text to judge.
        archetype : str
            The target behavioral archetype label.
        bias : str
            The target bias descriptor.
        model : str
            Which model acts as judge for this call. Not fixed at
            construction time: in self-critic mode the legacy app sets this
            to the student model just evaluated (``judge = student if
            self_critic else teacher_model``), so it can change every call
            within a single run/sweep.

        Returns
        -------
        JudgeVerdict
            The structured verdict.
        """
        ...


@runtime_checkable
class PromptStrategy(Protocol):
    """
    Builds the system prompt for one generation call, given an archetype,
    bias, and prompt-construction mode.

    Shaped by the existing per-iteration prompt construction in
    ``streamlit_app.py`` lines 901-930 (the three ``prompt_strategy``
    branches, each interpolating ``ARCHETYPES`` data).
    """

    def build(
        self,
        archetype: str,
        bias: str,
        mode: PromptMode,
        *,
        exclude_archetype_from_prompt: bool = False,
    ) -> str:
        """
        Build the system prompt text for one generation call.

        Parameters
        ----------
        archetype : str
            Target behavioral archetype label.
        bias : str
            Target bias descriptor, injected into the prompt.
        mode : PromptMode
            Which of the three construction strategies to use.
        exclude_archetype_from_prompt : bool, optional
            Only meaningful for :attr:`PromptMode.TUNED` -- omits the
            literal archetype name from the generated text.

        Returns
        -------
        str
            The system prompt.
        """
        ...


@runtime_checkable
class KnowledgeBase(Protocol):
    """
    Retrieval interface for the RAG knowledge base. Kept separate from
    :class:`Repository` -- retrieving reference knowledge chunks and
    persisting experiment results are unrelated concerns that happen to
    both be "storage" in the loosest sense.

    Shaped by the existing ``core.adapters.rag.ingestion.RAGEngine.retrieve`` method,
    whose return shape (``archetype``/``category``/``content``/``text``
    keys) is preserved here.
    """

    def retrieve(self, query: str, top_k: int = 5, archetype: Optional[str] = None) -> list[dict]:
        """
        Retrieve the top-k most relevant knowledge chunks for ``query``.

        Parameters
        ----------
        query : str
            The retrieval query text.
        top_k : int, optional
            Number of chunks to return.
        archetype : str, optional
            If given, restrict results to this archetype's chunks.

        Returns
        -------
        list[dict]
            Chunks as ``{"archetype", "category", "content", "text"}`` dicts.
        """
        ...


@runtime_checkable
class Repository(Protocol):
    """
    Persists run metadata and per-response records.

    Two adapters implement this over very different storage strategies
    (Stage 3): ``JSONLStore`` ports the existing flat-JSONL-row-per-response
    pattern; ``SQLiteRepo`` normalizes run metadata into its own table,
    directly motivated by Stage 0's finding that repeating it on every
    response row wastes ~21% of file bytes on a real export. Both satisfy
    the same interface so callers (``ExperimentRunner``, ``MetricsEngine``)
    do not need to know which storage strategy is active.

    Response records are intentionally typed as plain ``dict`` here, not a
    dedicated entity -- ``core.domain`` must not depend on the legacy
    ``core.analysis.data_contract.LabSchema`` (an outer-layer module not yet
    migrated), and defining a superseding ``ResponseRecord`` entity is
    deferred to whichever later stage actually needs to enforce that shape.
    """

    def save_run(self, run: RunRecord) -> str:
        """
        Persist a run's metadata.

        Parameters
        ----------
        run : RunRecord
            The run metadata to persist.

        Returns
        -------
        str
            The run's ID (echoing ``run.run_id`` for JSONL-style adapters,
            or a storage-assigned ID for others).
        """
        ...

    def save_response(self, run_id: str, response: dict) -> None:
        """
        Persist one response record, associated with a run.

        Parameters
        ----------
        run_id : str
            The owning run's ID.
        response : dict
            The response record to persist.
        """
        ...

    def load_responses(self, run_id: Optional[str] = None) -> list[dict]:
        """
        Load response records, optionally filtered to one run.

        Parameters
        ----------
        run_id : str, optional
            If given, return only that run's responses; otherwise return
            all responses across all runs.

        Returns
        -------
        list[dict]
            The matching response records.
        """
        ...

    def list_runs(self) -> "list[RunRecord]":
        """
        List every run's metadata known to this repository.

        Notes
        -----
        Added for Stage 7 (``tab_perf``): a read-side view needs some way to
        discover which runs exist before it can summarize one, which neither
        ``save_response`` nor ``load_responses`` provides on their own.

        Returns
        -------
        list[RunRecord]
            One entry per run that has had :meth:`save_run` called, ordered
            most-recent-``started_at``-first.
        """
        ...


__all__ = ["LLMClient", "Judge", "PromptStrategy", "KnowledgeBase", "Repository"]
