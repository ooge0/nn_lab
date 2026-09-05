"""
Unit tests for :func:`core.adapters._openai_compat.chat_complete` -- the
shared call logic behind both ``LLMClient`` adapters, tested in isolation
against a fake client (no real network).
"""

from core.adapters._openai_compat import chat_complete
from core.domain.entities import GenerationResult


def test_chat_complete_sends_system_and_user_messages(fake_openai_client):
    """The system and user prompts are sent as separate role-tagged messages, matching the legacy call shape."""
    client = fake_openai_client()
    chat_complete(client, "qwen:latest", "system text", "user text")

    assert client.calls[0]["messages"] == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "user text"},
    ]


def test_chat_complete_passes_sampling_params_through(fake_openai_client):
    """Sampling parameters are forwarded to the underlying call unchanged."""
    client = fake_openai_client()
    chat_complete(
        client,
        "qwen:latest",
        "sys",
        "user",
        temperature=0.3,
        top_p=0.8,
        frequency_penalty=1.1,
        presence_penalty=0.2,
        max_tokens=256,
        seed=42,
    )

    call = client.calls[0]
    assert call["temperature"] == 0.3
    assert call["top_p"] == 0.8
    assert call["frequency_penalty"] == 1.1
    assert call["presence_penalty"] == 0.2
    assert call["max_tokens"] == 256
    assert call["seed"] == 42


def test_chat_complete_json_mode_sets_response_format(fake_openai_client):
    """json_mode=True requests {'type': 'json_object'}, matching the legacy 'Return JSON' prompts."""
    client = fake_openai_client()
    chat_complete(client, "qwen:latest", "sys", "user", json_mode=True)
    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_chat_complete_no_json_mode_sends_none_response_format(fake_openai_client):
    """json_mode=False (default) sends response_format=None, matching the legacy generation call."""
    client = fake_openai_client()
    chat_complete(client, "qwen:latest", "sys", "user")
    assert client.calls[0]["response_format"] is None


def test_chat_complete_returns_generation_result_with_raw_text(fake_openai_client):
    """The returned GenerationResult carries the raw (unparsed) response content and the model name."""
    client = fake_openai_client('{"text": "hello"}')
    result = chat_complete(client, "qwen:latest", "sys", "user")

    assert isinstance(result, GenerationResult)
    assert result.text == '{"text": "hello"}'
    assert result.model == "qwen:latest"
    assert result.duration_ms >= 0
