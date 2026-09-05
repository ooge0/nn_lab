"""
Unit tests for :class:`core.adapters.ollama_client.OllamaClient` -- client
construction (native-API host derivation from config) and that
``generate()`` maps Ollama's native ``ChatResponse`` fields onto
``GenerationResult`` correctly, including the performance-telemetry fields
added when this adapter switched from the OpenAI-compatible endpoint to
Ollama's native ``/api/chat`` (the compat endpoint's response has no
token-count or timing-breakdown fields at all -- confirmed by querying both
live and comparing the raw JSON, not assumed). No real network: the
constructed ``ollama.Client`` is swapped for a fake after construction,
since building the client object itself makes no network call.
"""

from core.adapters.ollama_client import OllamaClient, _native_host
from utils import config_loader_short


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChatResponse:
    """Mimics ollama.ChatResponse's attribute shape closely enough to test the mapping in OllamaClient.generate()."""

    def __init__(self, content, **kwargs):
        self.message = FakeMessage(content)
        self.total_duration = kwargs.get("total_duration")
        self.load_duration = kwargs.get("load_duration")
        self.prompt_eval_count = kwargs.get("prompt_eval_count")
        self.prompt_eval_duration = kwargs.get("prompt_eval_duration")
        self.eval_count = kwargs.get("eval_count")
        self.eval_duration = kwargs.get("eval_duration")


class FakeOllamaClient:
    """Records every chat() call's kwargs and returns a fixed FakeChatResponse."""

    def __init__(self, response=None):
        self.calls = []
        self._response = response or FakeChatResponse("stub")

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_native_host_strips_v1_suffix_from_the_openai_compat_base_url():
    """_native_host derives Ollama's native-API host from the existing [OLLAMA] openai_base_url, not a separate config value."""
    assert _native_host("http://localhost:11434/v1") == "http://localhost:11434"


def test_native_host_leaves_a_url_without_v1_suffix_unchanged():
    """A base URL that doesn't end in /v1 (unexpected, but shouldn't crash) passes through as-is."""
    assert _native_host("http://localhost:11434") == "http://localhost:11434"


def test_constructs_with_the_native_host_derived_from_configured_credentials():
    """The underlying ollama.Client is built from config.ini's [OLLAMA] section, native host (no /v1)."""
    client = OllamaClient()
    assert client._client._client.base_url is not None
    expected = _native_host(config_loader_short.OPENAI_BASE_URL)
    assert str(client._client._client.base_url).rstrip("/") == expected.rstrip("/")


def test_generate_returns_text_and_model():
    """generate() forwards to the swapped-in client and returns its content as a GenerationResult."""
    client = OllamaClient()
    client._client = FakeOllamaClient(FakeChatResponse('{"text": "styled response"}'))

    result = client.generate("qwen:latest", "sys prompt", "user prompt", temperature=0.5)

    assert result.text == '{"text": "styled response"}'
    assert result.model == "qwen:latest"
    assert client._client.calls[0]["options"]["temperature"] == 0.5


def test_generate_sends_system_and_user_as_separate_messages():
    """The system and user prompts are sent as separate role-tagged messages, matching the legacy call shape."""
    client = OllamaClient()
    client._client = FakeOllamaClient()

    client.generate("qwen:latest", "system prompt", "user prompt")

    messages = client._client.calls[0]["messages"]
    assert messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]


def test_generate_json_mode_requests_json_format():
    """json_mode=True requests format='json', the native-API equivalent of the compat endpoint's response_format."""
    client = OllamaClient()
    client._client = FakeOllamaClient()

    client.generate("qwen:latest", "sys", "user", json_mode=True)

    assert client._client.calls[0]["format"] == "json"


def test_generate_no_json_mode_sends_none_format():
    """json_mode=False (default) sends format=None."""
    client = OllamaClient()
    client._client = FakeOllamaClient()

    client.generate("qwen:latest", "sys", "user")

    assert client._client.calls[0]["format"] is None


def test_generate_maps_token_counts_from_the_native_response():
    """prompt_tokens/completion_tokens come from Ollama's own prompt_eval_count/eval_count -- real counts, not a word-count proxy."""
    client = OllamaClient()
    client._client = FakeOllamaClient(FakeChatResponse("hi", prompt_eval_count=22, eval_count=3))

    result = client.generate("qwen:latest", "sys", "user")

    assert result.prompt_tokens == 22
    assert result.completion_tokens == 3


def test_generate_converts_ollama_nanosecond_durations_to_milliseconds():
    """The ollama_*_duration_ms fields are Ollama's own nanosecond fields divided by 1e6, not otherwise altered."""
    client = OllamaClient()
    client._client = FakeOllamaClient(
        FakeChatResponse(
            "hi",
            total_duration=99_636_200,
            load_duration=3_405_000,
            prompt_eval_duration=45_313_000,
            eval_duration=38_281_000,
        )
    )

    result = client.generate("qwen:latest", "sys", "user")

    assert result.ollama_total_duration_ms == 99.6362
    assert result.ollama_load_duration_ms == 3.405
    assert result.ollama_prompt_eval_duration_ms == 45.313
    assert result.ollama_eval_duration_ms == 38.281


def test_generate_leaves_ollama_fields_none_when_the_response_omits_them():
    """A response missing the performance fields (e.g. a stub/older server) leaves them None rather than crashing."""
    client = OllamaClient()
    client._client = FakeOllamaClient(FakeChatResponse("hi"))

    result = client.generate("qwen:latest", "sys", "user")

    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.ollama_total_duration_ms is None
    assert result.ollama_eval_duration_ms is None
