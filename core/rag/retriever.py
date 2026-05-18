"""
retriever.py

Lightweight retrieval interface for LLM integration.
Provides prompt-ready context building.
"""

from typing import List, Dict

from core.rag.ingestion import RAGEngine



class Retriever:
    """
    Converts retrieval results into LLM-ready context.
    """

    def __init__(self, rag_engine: RAGEngine):
        self.rag = rag_engine

    def retrieve(self, query: str, k: int = 5) -> List[Dict]:
        """
        Get raw retrieved chunks.

        Args:
            query: user input
            k: top-k retrieval

        Returns:
            list of dict chunks
        """
        return self.rag.query(query, k=k)

    def build_context(self, query: str, k: int = 5) -> str:
        """
        Build formatted context string for LLM prompt injection.

        Returns:
            formatted string context block
        """

        results = self.retrieve(query, k=k)

        context_lines = []

        for r in results:
            line = f"[{r['archetype']} | {r['domain']}] {r['content']}"
            context_lines.append(line)

        return "\n".join(context_lines)