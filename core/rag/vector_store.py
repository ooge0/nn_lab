"""
vector_store.py

FAISS-based vector storage for semantic retrieval.
Handles embedding creation and nearest neighbor search.
"""

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict

from core.rag.chunking import Chunk

class FAISSVectorStore:
    """
    Vector store using FAISS for fast similarity search.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Args:
            model_name: SentenceTransformer model name
        """
        self.model = SentenceTransformer(model_name)

        self.index = None
        self.chunks: List[Chunk] = []
        self.embeddings = None

    def build(self, chunks: List[Chunk]):
        """
        Build FAISS index from chunks.

        Args:
            chunks: list of structured knowledge chunks
        """

        self.chunks = chunks

        # Convert chunks to embedding input
        texts = [
            f"{c.archetype} | {c.domain} | {c.content}"
            for c in chunks
        ]

        # Generate embeddings
        self.embeddings = self.model.encode(texts)
        self.embeddings = np.array(self.embeddings).astype("float32")

        dim = self.embeddings.shape[1]

        # FAISS index (L2 distance)
        self.index = faiss.IndexFlatL2(dim)
        self.index.add(self.embeddings)

    def search(self, query: str, k: int = 5) -> List[Dict]:
        """
        Perform semantic search over knowledge base.

        Args:
            query: user query
            k: number of results

        Returns:
            List of matched chunks with metadata
        """

        query_vec = self.model.encode([query]).astype("float32")

        distances, indices = self.index.search(query_vec, k)

        results = []

        for idx in indices[0]:
            chunk = self.chunks[idx]

            results.append({
                "archetype": chunk.archetype,
                "domain": chunk.domain,
                "content": chunk.content
            })

        return results