"""
core.adapters._openai_compat
==============================

Call logic for ``LLMClient`` adapters that talk to an OpenAI-compatible
chat-completions endpoint. Currently used by :mod:`ollama_client` (Ollama's
own compat endpoint, the only backend in scope for now); kept as its own
module, separate from client construction, so it stays a one-line addition
if a second OpenAI-compatible backend is ever needed.

Leading underscore: private to ``core.adapters``, not part of the public
adapter surface.
"""

import time

from openai import OpenAI

from core.domain.entities import GenerationResult


def chat_complete(
    client: OpenAI,
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
    """
    Issue one chat-completion call, matching the exact request shape used by
    the legacy generation call (``streamlit_app.py`` lines 953-961) and
    validator call (lines 982-994).

    Parameters
    ----------
    client : openai.OpenAI
        A configured client (base URL + API key already set).
    model : str
        Model name to call.
    system_prompt, user_prompt : str
        Message contents.
    temperature, top_p, frequency_penalty, presence_penalty : float, optional
        Sampling parameters, passed through as-is.
    max_tokens : int, optional
        Generation token cap.
    seed : int, optional
        Generation seed.
    json_mode : bool, optional
        If ``True``, requests ``response_format={"type": "json_object"}``.

    Returns
    -------
    GenerationResult
        Raw response text and wall-clock duration in milliseconds.
    """
    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # A plain dict is accepted at runtime (and by test doubles), but the
        # SDK's overloaded type stubs want a ResponseFormatJSONObject
        # instance specifically -- not worth fighting for a value this shape.
        response_format={"type": "json_object"} if json_mode else None,  # type: ignore[call-overload]
        temperature=temperature,
        top_p=top_p,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        max_tokens=max_tokens,
        seed=seed,
    )
    duration_ms = (time.time() - start) * 1000
    return GenerationResult(
        text=response.choices[0].message.content,
        duration_ms=duration_ms,
        model=model,
    )
