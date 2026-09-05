"""
core.adapters.ollama_client
=============================

``LLMClient`` implementation targeting Ollama's own **native** API
(``/api/chat``, via the official ``ollama`` Python package -- already a
direct dependency, previously only used by the legacy app's model-management
calls). Switched from the OpenAI-compatible endpoint specifically to get
real per-call performance data Ollama only reports natively: token counts
and a load-time/prompt-eval-time/generation-time breakdown (see
:class:`~core.domain.entities.GenerationResult`'s new optional fields) --
the compat endpoint's response has none of this, confirmed by querying both
live and comparing the raw JSON. Everything else about this adapter's
behaviour (which model, what gets sent, sampling params) is unchanged.

The judge (:mod:`core.adapters.structured_judge`) still goes through the
OpenAI-compatible endpoint via :mod:`core.adapters._openai_compat`, on
purpose -- performance telemetry is about the student model being
evaluated, not the judge doing the evaluating; no reason to touch a working,
tested call site for a metric nothing asks of it.
"""

import time
from urllib.parse import urlsplit, urlunsplit

import ollama

from core.domain.entities import GenerationResult
from utils import config_loader_short


def _native_host(openai_compat_base_url: str) -> str:
    """
    Derive Ollama's native-API host from the openai-compat base URL.

    Parameters
    ----------
    openai_compat_base_url : str
        E.g. ``"http://localhost:11434/v1"`` (``config.ini``'s
        ``[OLLAMA] openai_base_url``).

    Returns
    -------
    str
        The same host with any trailing ``/v1`` path stripped, e.g.
        ``"http://localhost:11434"`` -- derived from the one existing config
        value rather than adding a second one that could drift out of sync.
    """
    parts = urlsplit(openai_compat_base_url)
    path = parts.path[: -len("/v1")] if parts.path.endswith("/v1") else parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class OllamaClient:
    """
    ``LLMClient`` for local Ollama models, via Ollama's native ``/api/chat``.

    Notes
    -----
    Host is derived from ``utils.config_loader_short.OPENAI_BASE_URL``
    (``config/config.ini``'s ``[OLLAMA]`` section) -- same config value the
    judge/legacy code already reads, just with the openai-compat ``/v1``
    suffix stripped. No API key: Ollama's native API has no auth concept for
    local use.
    """

    def __init__(self) -> None:
        self._client = ollama.Client(host=_native_host(config_loader_short.OPENAI_BASE_URL))

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
        max_tokens: "int | None" = None,
        seed: "int | None" = None,
        json_mode: bool = False,
    ) -> GenerationResult:
        """See :meth:`core.domain.interfaces.LLMClient.generate`."""
        start = time.time()
        response = self._client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json" if json_mode else None,
            options={
                "temperature": temperature,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
                "num_predict": max_tokens,
                "seed": seed,
            },
        )
        duration_ms = (time.time() - start) * 1000

        def _ms(nanoseconds: "int | None") -> "float | None":
            return nanoseconds / 1_000_000 if nanoseconds is not None else None

        return GenerationResult(
            # response.message.content is typed Optional by the ollama package (e.g. a
            # tool-call-only response can leave it unset) -- GenerationResult.text requires
            # str, so an unguarded None here would raise a pydantic ValidationError deep
            # inside ExperimentRunner._run_one instead of being handled as an empty response.
            text=response.message.content or "",
            duration_ms=duration_ms,
            model=model,
            prompt_tokens=response.prompt_eval_count,
            completion_tokens=response.eval_count,
            ollama_total_duration_ms=_ms(response.total_duration),
            ollama_load_duration_ms=_ms(response.load_duration),
            ollama_prompt_eval_duration_ms=_ms(response.prompt_eval_duration),
            ollama_eval_duration_ms=_ms(response.eval_duration),
        )
