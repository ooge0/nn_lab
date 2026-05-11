import os
import pytest

from core.rag.ingestion import RAGEngine


@pytest.fixture(scope="session")
def rag():
    """
    Shared RAG fixture for all tests. Fixture initializes RAG system once per test module.
    """

    engine = RAGEngine()

    base_dir = os.path.dirname(os.path.dirname(__file__))
    knowledge_path = os.path.join(base_dir, "knowledge")
    print(f"knowledge_path : {knowledge_path}")
    engine.load_knowledge_base(knowledge_path)

    return engine