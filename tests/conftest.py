import os
import sys

import pytest

# Add the project root (one level up from /test) to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Now the imports will work
from core.adapters.rag.ingestion import RAGEngine


@pytest.fixture(scope="session", autouse=True)
def _warm_lazy_singleton_models():
    """
    Force this project's three lazy-loaded, process-wide model singletons (the sentence-embedding
    model behind ``semantic_overlap``/RAG, the spaCy+TextDescriptives pipeline behind
    ``dependency_distance``, and the NLI cross-encoder behind ``check_hallucination``) to load
    once, at session start, rather than on whichever test happens to touch them first.

    Found 2026-08-24 while adding ``dependency_distance``: ``tests/integration
    /test_experiments_api.py::test_stop_mid_run_returns_200_and_the_run_actually_halts_early``
    polls for up to 5 seconds waiting for a background run to finish -- fine when the process's
    models are already warm, but a genuinely cold first load measured ~19s (embedder), ~18s (NLI
    cross-encoder), and ~4s (spaCy), each timed standalone -- all three comfortably blow that
    budget. This was *already* a latent, order-dependent fragility before this fix (the embedder's
    own cold-load already exceeded the timeout on its own): the full suite happened to pass because
    some earlier test always warmed the models first, but nothing guaranteed that ordering, and
    running a narrower test selection (or a different pytest version's default collection order)
    could fail the exact same way. This fixture removes the dependency on incidental ordering
    rather than papering over one specific timing-sensitive test.
    """
    from core.analysis.calculate_advanced_linguistic_metrics import _get_embedder
    from core.analysis.hallucination_check import check_hallucination
    from core.analysis.syntactic_complexity import dependency_distance

    _get_embedder()
    dependency_distance("warm up the spaCy pipeline once")
    check_hallucination("warm up the NLI model once", "so the first real test doesn't pay this cost")


@pytest.fixture(scope="session")
def rag():
    """
    Shared RAG fixture for all tests. Fixture initializes RAG system once per test module.
    """

    engine = RAGEngine()

    base_dir = os.path.dirname(os.path.dirname(__file__))
    knowledge_path = os.path.join(base_dir, "knowledge/rag")
    print(f"knowledge_path : {knowledge_path}")
    engine.load_knowledge_base(knowledge_path)

    return engine


class FakeOpenAIClient:
    """
    Test double matching the shape of ``openai.OpenAI().chat.completions
    .create(...)`` closely enough to test ``core.adapters._openai_compat
    .chat_complete`` and the ``LLMClient`` adapters built on it, without
    any real network call.

    Records every call's keyword arguments in ``self.calls`` so tests can
    assert on the exact request shape sent, and returns ``response_content``
    (default ``'{"ok": true}'``) as the completion's message content.
    """

    def __init__(self, response_content: str = '{"ok": true}'):
        self.response_content = response_content
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": self.response_content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


@pytest.fixture
def fake_openai_client():
    """Factory fixture: call with an optional response_content string to get a fresh FakeOpenAIClient."""
    return FakeOpenAIClient
