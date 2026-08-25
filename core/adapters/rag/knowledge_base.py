"""
core.adapters.rag.knowledge_base
===================================

``KnowledgeBase`` adapter wrapping :class:`~core.adapters.rag.ingestion
.RAGEngine`. A thin, explicit boundary: ``RAGEngine.retrieve`` is already
structurally close to the ``KnowledgeBase`` interface (same return shape),
but this wrapper makes the parameter rename (``text`` -> ``query``) and the
adapter relationship intentional rather than incidental.
"""

from typing import Optional

from core.adapters.rag.ingestion import RAGEngine


class RAGKnowledgeBase:
    """
    ``KnowledgeBase`` backed by :class:`~core.adapters.rag.ingestion.RAGEngine`.

    Parameters
    ----------
    rag_engine : RAGEngine, optional
        An already-built engine (with its knowledge base loaded). If
        omitted, a fresh, unloaded ``RAGEngine`` is constructed --
        :meth:`load_knowledge_base` must be called before
        :meth:`retrieve` will return anything.
    """

    def __init__(self, rag_engine: Optional[RAGEngine] = None) -> None:
        self._rag_engine = rag_engine if rag_engine is not None else RAGEngine()

    def load_knowledge_base(self, folder_path: str) -> None:
        """Build the underlying index. See ``RAGEngine.load_knowledge_base``."""
        self._rag_engine.load_knowledge_base(folder_path)

    def retrieve(self, query: str, top_k: int = 5, archetype: Optional[str] = None) -> "list[dict]":
        """See :meth:`core.domain.interfaces.KnowledgeBase.retrieve`."""
        # RAGEngine.retrieve's own signature types `archetype` as `str = None`
        # (an implicit-Optional pre-existing in the relocated-as-is legacy
        # code, not touched here) -- mypy takes that literally as `str`.
        return self._rag_engine.retrieve(text=query, top_k=top_k, archetype=archetype)  # type: ignore[arg-type]
