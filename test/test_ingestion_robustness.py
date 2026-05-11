import pytest
import os
import shutil
from core.rag.ingestion import RAGEngine


# ====================================================
# FIXTURES: Setting up temporary test environments
# ====================================================

@pytest.fixture
def temp_knowledge_base(tmp_path):
    """Creates a temporary folder with valid and invalid files."""
    kb_dir = tmp_path / "knowledge"
    kb_dir.mkdir()

    # 1. Valid File
    schizoid_file = kb_dir / "schizoid.txt"
    schizoid_file.write_text("Behavior|Abstract thinking.\nSpeech|Minimalist.", encoding="utf-8")

    # 2. Empty File (The 'Silent Failure' test)
    empty_file = kb_dir / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    # 3. Malformed File (No pipes/colons)
    bad_file = kb_dir / "bad_format.txt"
    bad_file.write_text("This line has no delimiter", encoding="utf-8")

    return str(kb_dir)


# ====================================================
# TESTS: Ingestion & Chanking Logic
# ====================================================

def test_load_knowledge_base_error_handling(temp_knowledge_base):
    """Verify engine raises correct errors for missing or empty paths."""
    rag = RAGEngine()

    # Test 1: Non-existent folder
    with pytest.raises(FileNotFoundError):
        rag.load_knowledge_base("./non_existent_folder")

    # Test 2: Valid load (should skip empty/bad files and not crash)
    rag.load_knowledge_base(temp_knowledge_base)
    assert hasattr(rag.store, 'index')


def test_metadata_integrity(temp_knowledge_base):
    """Best Practice: Ensure psychotype label is correctly mapped from filename."""
    rag = RAGEngine()
    rag.load_knowledge_base(temp_knowledge_base)

    # Query for content we know is in schizoid.txt
    results = rag.query("Abstract thinking", k=1)

    assert len(results) > 0
    # Ensure the engine derived 'schizoid' from 'schizoid.txt'
    assert results[0]["psychotype"] == "schizoid"
    assert results[0]["domain"] == "Behavior"


def test_retrieval_isolation_negative(temp_knowledge_base):
    """
    Critical Test: Ensure that asking for a psychotype that exists
    returns data, but asking for one that doesn't returns an empty list
    (Isolation check).
    """
    rag = RAGEngine()
    rag.load_knowledge_base(temp_knowledge_base)

    # Request 'paranoid' but we only loaded 'schizoid'
    results = rag.retrieve("some text", top_k=5, psychotype="paranoid")

    assert len(results) == 0, "Should not leak other psychotypes when a filter is applied."


def test_chunk_granularity(temp_knowledge_base):
    """Verify that every line in a file is treated as a unique chunk."""
    rag = RAGEngine()
    rag.load_knowledge_base(temp_knowledge_base)

    # schizoid.txt had 2 valid lines
    # We use a broad query to get everything
    all_schizoid = rag.retrieve("thinking minimalist", top_k=10, psychotype="schizoid")

    assert len(all_schizoid) >= 2, "Chunker is missing lines from the source file."


def test_query_before_load_safety():
    """Ensure the app doesn't crash if a user triggers a query before RAG is loaded."""
    rag = RAGEngine()
    # No load_knowledge_base called
    results = rag.query("test")
    assert results == [], "Engine should return empty list, not crash, if index is missing."
