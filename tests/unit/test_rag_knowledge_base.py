"""
Unit tests for :class:`core.adapters.rag.knowledge_base.RAGKnowledgeBase` --
the KnowledgeBase adapter wrapping RAGEngine, tested against a fake engine
(no real embeddings/FAISS index needed here; that's already covered by the
existing ``test_rag.py``/``test_rag_logic.py`` suites against the real
engine).
"""

from core.adapters.rag.knowledge_base import RAGKnowledgeBase


class FakeRAGEngine:
    """Records the exact call RAGKnowledgeBase.retrieve() makes into RAGEngine.retrieve()."""

    def __init__(self):
        self.calls = []
        self.loaded_path = None

    def retrieve(self, text, top_k=5, archetype=None, **kwargs):
        self.calls.append({"text": text, "top_k": top_k, "archetype": archetype})
        return [{"archetype": archetype or "Detached", "category": "Behavior", "content": "c", "text": "c"}]

    def load_knowledge_base(self, folder_path):
        self.loaded_path = folder_path


def test_retrieve_renames_query_to_text_for_the_underlying_engine():
    """RAGKnowledgeBase.retrieve(query=...) calls RAGEngine.retrieve(text=...) -- the interface's parameter rename."""
    fake = FakeRAGEngine()
    kb = RAGKnowledgeBase(rag_engine=fake)

    kb.retrieve("detached signaling", top_k=3, archetype="Detached")

    assert fake.calls == [{"text": "detached signaling", "top_k": 3, "archetype": "Detached"}]


def test_retrieve_default_top_k_and_archetype():
    """retrieve() with only a query uses the documented defaults (top_k=5, archetype=None)."""
    fake = FakeRAGEngine()
    kb = RAGKnowledgeBase(rag_engine=fake)

    kb.retrieve("query text")

    assert fake.calls == [{"text": "query text", "top_k": 5, "archetype": None}]


def test_load_knowledge_base_delegates_to_the_engine():
    """load_knowledge_base() forwards the folder path to RAGEngine.load_knowledge_base()."""
    fake = FakeRAGEngine()
    kb = RAGKnowledgeBase(rag_engine=fake)

    kb.load_knowledge_base("knowledge/rag")

    assert fake.loaded_path == "knowledge/rag"


def test_without_an_injected_engine_a_real_ragengine_is_constructed():
    """RAGKnowledgeBase() with no engine builds a real (unloaded) RAGEngine, not None."""
    from core.adapters.rag.ingestion import RAGEngine

    kb = RAGKnowledgeBase()
    assert isinstance(kb._rag_engine, RAGEngine)
