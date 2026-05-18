import logging
import os
from typing import List

from core.rag.chunking import Chunk, parse_txt_file
from core.rag.vector_store import FAISSVectorStore

# Set up logging for better debugging in console
logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self):
        self.store = FAISSVectorStore()

    def load_knowledge_base(self, folder_path: str):
        # 1. Path existence check
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Knowledge folder not found: {os.path.abspath(folder_path)}")

        all_chunks: List[Chunk] = []

        # 2. Collect files and handle empty directory
        try:
            files = [f for f in os.listdir(folder_path) if f.endswith(".txt")]
        except Exception as e:
            raise RuntimeError(f"Failed to read directory: {e}")

        if not files:
            # We raise a custom error here so the Streamlit UI can catch it
            raise ValueError(f"No .txt files found in {folder_path}. Please add knowledge files.")

        for file_name in files:
            archetype = file_name.replace(".txt", "")
            file_path = os.path.join(folder_path, file_name)

            try:
                chunks = parse_txt_file(file_path, archetype)
                if chunks:
                    all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"Failed to parse {file_name}: {e}")
                continue

        # 3. Final validation before building index
        if not all_chunks:
            raise ValueError("Found .txt files, but no text content could be extracted into chunks.")

        # 4. Safe build call
        try:
            self.store.build(all_chunks)
        except Exception as e:
            # This catches the "tuple index out of range" if the vector store still fails
            raise RuntimeError(f"Vector Store build failed: {e}")

    def retrieve_old(self, text: str, top_k: int = 5, archetype: str = None, **kwargs):
        raw_results = self.query(text, k=top_k * 5)

        if archetype:
            # Match archetype exactly
            filtered = [r for r in raw_results if r["archetype"].lower() == archetype.lower()]
            return filtered[:top_k]

        return raw_results[:top_k]

    def retrieve(self, text: str, top_k: int = 5, archetype: str = None, **kwargs):
        raw_results = self.query(text, k=top_k * 5)

        if archetype:
            raw_results = [r for r in raw_results if r["archetype"].lower() == archetype.lower()]

        final_results = []
        for r in raw_results[:top_k]:
            # We map 'domain' to 'category' AND 'content' to 'text'
            # This makes the chunk compatible with all parts of your app
            final_results.append({
                "archetype": r.get("archetype"),
                "category": r.get("domain"),  # Map 'domain' to 'category'
                "content": r.get("content"),
                "text": r.get("content")
            })

        return final_results

    def query(self, text: str, k: int = 5):
        """Internal search logic using the FAISS index."""
        if not hasattr(self.store, 'index') or self.store.index is None:
            logger.warning("Query attempted before RAG index was built.")
            return []
        return self.store.search(text, k=k)
