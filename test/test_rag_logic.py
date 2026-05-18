# tests/test_rag_logic.py

def test_filtered_semantic_retrieval_old(rag):
    """
    Test that filtering correctly isolates the target archetype
    even when 'baseline' has similar semantic content.
    """
    query_text = "conceptual focus and low social engagement"

    # Pass the archetype filter explicitly
    results = rag.retrieve(text=query_text, top_k=3, archetype="schizoid")

    assert len(results) > 0
    assert results[0]["archetype"] == "schizoid", "Filter failed to isolate schizoid"
    assert "conceptual" in results[0]["content"].lower() or "abstract" in results[0]["content"].lower()


def test_filtered_semantic_retrieval(rag):
    query_text = "conceptual focus and low social engagement"
    results = rag.retrieve(text=query_text, top_k=3, archetype="schizoid")

    assert len(results) > 0
    hit = results[0]

    # Verify metadata
    assert hit["archetype"] == "schizoid"

    # Verify content relevance using keywords instead of exact string
    content = hit["content"].lower()
    keywords = ["social", "engagement", "abstract", "conceptual", "signaling"]

    assert any(k in content for k in keywords), f"Unexpected content: {content}"


def test_unfiltered_retrieval_ranking(rag):
    """
    Debug test: See what is actually coming back first when unfiltered.
    """
    results = rag.retrieve("conceptual focus", top_k=1)
    # This helps you see if your embeddings are 'too flat'
    # (i.e., different archetypes look too similar to the model)
    print(f"Top unfiltered hit: {results[0]['archetype']} -> {results[0]['content']}")


def test_empty_query_handling(rag):
    """Ensure the system doesn't crash on empty or nonsensical input."""
    results = rag.retrieve(text="", top_k=5)
    assert isinstance(results, list), "Should return a list even if query is empty."
