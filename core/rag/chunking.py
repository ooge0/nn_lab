"""
chunking.py

Responsible for converting raw .txt knowledge files
into structured atomic chunks suitable for embeddings.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    """
    Represents a single atomic knowledge unit for RAG.

    Attributes:
        psychotype: target psychotype label (e.g. paranoid, schizoid)
        domain: semantic domain (behavior, speech, cognition, trigger, emotion)
        content: atomic statement used for embedding
    """
    psychotype: str
    domain: str
    content: str


def parse_txt_file(file_path: str, psychotype: str) -> List[Chunk]:
    chunks = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Try to split by pipe (|) or colon (:)
            delimiter = None
            if "|" in line:
                delimiter = "|"
            elif ":" in line:
                delimiter = ":"

            try:
                if delimiter:
                    domain, content = line.split(delimiter, 1)
                    domain_val = domain.strip()
                    content_val = content.strip()
                else:
                    # Fallback for plain lines
                    domain_val = "General"
                    content_val = line

                chunks.append(
                    Chunk(
                        psychotype=psychotype,
                        domain=domain_val,
                        content=content_val
                    )
                )
            except Exception:
                continue

    return chunks
