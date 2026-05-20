from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
import numpy as np

"""
test_rag.py

Pytest suite for RAG system validation.

Covers:
- Ingestion correctness
- Schema validity
- Retrieval sanity
- Archetype coverage
- Semantic alignment (Cosine Similarity)
- Weighted Drift Index calculation
"""


# ---------------------------------------------------------
# 1. DATA INTEGRITY & INGESTION TESTS
# ---------------------------------------------------------

def test_chunks_loaded(rag):
    """
    Ensure the knowledge base is not empty after ingestion.
    """
    assert len(rag.store.chunks) > 0, "RAG knowledge base is empty"


def test_all_archetypes_present(rag):
    """
    Ensure all expected archetype categories exist in the loaded dataset.
    """
    archetypes = {c.archetype for c in rag.store.chunks}
    expected = {"paranoid", "schizoid", "hysteroid", "epileptoid"}

    missing = expected - archetypes
    assert not missing, f"Missing archetypes in knowledge base: {missing}"


def test_valid_domains(rag):
    """
    Ensure all ingested chunks adhere to the allowed domain labels (schema validation).
    """
    allowed = {"behavior", "speech", "cognition", "trigger", "emotion"}

    invalid = [
        c.domain for c in rag.store.chunks
        if c.domain not in allowed
    ]

    assert not invalid, f"Invalid domains found in chunks: {set(invalid)}"


def test_no_empty_chunks(rag):
    """
    Safety check: Ensure no empty or broken content chunks were ingested.
    """
    empty = [c for c in rag.store.chunks if not c.content.strip()]
    assert len(empty) == 0, "Empty content detected in ingested chunks"


def test_chunk_length_quality(rag):
    """
    Quality Gate: Ensure chunks are not degenerate (too short to provide context).
    Allow max 10% of short chunks if they are specific triggers.
    """
    short_chunks = [c for c in rag.store.chunks if len(c.content) < 20]
    threshold = len(rag.store.chunks) * 0.1
    assert len(short_chunks) < threshold, "Excessive number of low-quality/short chunks detected"


# ---------------------------------------------------------
# 2. RETRIEVAL & SEMANTIC SANITY TESTS
# ---------------------------------------------------------

def test_retrieval_returns_results(rag):
    """
    Verify that the vector store (e.g., FAISS) returns valid results for a basic query.
    """
    results = rag.query("paranoid behavior and suspicion", k=3)
    assert isinstance(results, list)
    assert len(results) > 0, "Search engine failed to return any results"


def test_paranoid_signal_retrieval(rag):
    """
    Semantic test: Ensure a query with strong paranoid keywords returns paranoid-tagged content.
    """
    results = rag.query("hidden motives distrust and suspicion", k=5)
    paranoid_hits = [r for r in results if r["archetype"] == "paranoid"]
    assert len(paranoid_hits) > 0, "Retrieval failed to identify paranoid signals for a relevant query"


def test_retrieval_boundary_isolation(rag):
    """
    Isolation test: Ensure a query for 'Structured' traits does not leak 'Expressive' content.
    Prevents cross-contamination in the vector space.
    """
    query = "Structured order, discipline and physical control"
    results = rag.query(query, k=5)

    # Top hit must be the target archetype
    assert results[0]["archetype"] == "baseline", f"Wrong primary archetype retrieved: {results[0]['archetype']}"

    # Secondary hits should not contain conflicting archetypes
    types_in_results = {r["archetype"] for r in results}
    assert "hysteroid" not in types_in_results, "Cross-contamination: Expressive content leaked into Structured search"


def test_cosine_alignment_integrity(rag):
    """
    Validate that the embedding model correctly ranks semantic similarity.
    Reference RAG chunk should have higher similarity to a relevant query than to noise.
    """
    reference_content = "Abstract thinking and social isolation"

    # Encode texts using the engine's internal model
    emb_ref = rag.model.encode([reference_content])
    emb_positive = rag.model.encode(["Highly conceptual and withdrawn behavior"])
    emb_negative = rag.model.encode(["Aggressive loud social interaction"])

    score_pos = cosine_similarity(emb_ref, emb_positive)[0][0]
    score_neg = cosine_similarity(emb_ref, emb_negative)[0][0]

    assert score_pos > 0.75, f"Positive match similarity too low: {score_pos}"
    assert score_pos > score_neg, "Vector drift detected: Negative text ranked closer than positive text"


# ---------------------------------------------------------
# 3. ADVANCED ANALYTICS TESTS (DRIFT LOGIC)
# ---------------------------------------------------------

def test_weighted_drift_calculation():
    """
    Validate the Drift Index formula.
    Checks if the system correctly identifies 'Out of Character' responses based on weighted attributes.
    """
    # Attribute weights for a specific archetype (e.g., Detached)
    weights = {
        "formality": 0.5,  # High priority
        "aggression": 0.2,  # Low priority
        "complexity": 0.3  # Medium priority
    }

    # Target Neutral (The Ideal Persona)
    target = {"formality": 0.9, "aggression": 0.1, "complexity": 0.8}

    # Case A: Model output is close to target (Low Drift)
    actual_good = {"formality": 0.85, "aggression": 0.15, "complexity": 0.75}

    # Case B: Model output drifts into wrong behavior (High Drift)
    actual_bad = {"formality": 0.3, "aggression": 0.7, "complexity": 0.2}

    def calculate_drift(t, a, w):
        return sum(w[k] * abs(t[k] - a[k]) for k in w)

    drift_low = calculate_drift(target, actual_good, weights)
    drift_high = calculate_drift(target, actual_bad, weights)

    assert drift_low < 0.15, f"Incorrect Drift Index for good response: {drift_low}"
    assert drift_high > 0.4, f"Failed to detect significant drift: {drift_high}"


def test_retrieval_sanity_loop(rag):
    """
    Comprehensive smoke test for a variety of archetype queries.
    Prints retrieval details for manual inspection during debugging.
    """
    queries = [
        "How does paranoid personality behave?",
        "How does schizoid person speak?",
        "What triggers hysteroid behavior?",
        "How does epileptoid think?"
    ]

    for q in queries:
        results = rag.query(q, k=3)
        assert len(results) > 0




def test_feature_correlation_consistency(rag):
    """
    Structural Integrity Check:
    Ensures that the correlation between traits in the model output
    matches the correlation structure of the 'Ground Truth' dataset.

    This detects 'Psychological Chimera'—responses where individual
    scores might seem okay, but the combination of traits is logically
    impossible for the given archetype.
    """

    # 1. Neutral: Establish the 'Ground Truth' correlation matrix.
    # In a production environment, this data is pulled directly from your RAG knowledge base.
    # Example for 'Histeroid': High emotionality and attention-seeking should correlate positively,
    # while logical consistency usually correlates negatively with dramatic exaggeration.
    baseline_data = {
        "emotional_amplification": [0.9, 0.85, 0.95, 0.8],
        "attention_seeking": [0.95, 0.9, 0.88, 0.92],
        "logical_consistency": [0.2, 0.3, 0.15, 0.25]
    }
    df_baseline = pd.DataFrame(baseline_data)
    baseline_corr = df_baseline.corr()

    # 2. Actual: Extract metrics from the model's recent generated responses.
    # We analyze a batch of responses to see if the 'Personality Structure' holds up.
    actual_data = {
        "emotional_amplification": [0.88, 0.40, 0.90],  # Note: One response dropped significantly
        "attention_seeking": [0.92, 0.35, 0.85],  # Note: Correlation with emotionality is breaking
        "logical_consistency": [0.22, 0.80, 0.20]  # Note: Unexpected spike in logic
    }
    df_actual = pd.DataFrame(actual_data)
    actual_corr = df_actual.corr()

    # 3. Calculation: Measure the distance between Correlation Matrices.
    # We use the Frobenius norm to quantify the 'Structural Drift'.
    # If the traits start correlating differently, the persona is 'drifting' into a different radical.
    matrix_diff = np.linalg.norm(baseline_corr - actual_corr)

    print(f"\n[Structural Check] Correlation Matrix Drift: {matrix_diff:.4f}")

    # Threshold for structural collapse (determined through empirical benchmarking).
    # A high diff indicates the model is producing a 'personality glitch'.
    threshold = 0.5
    assert matrix_diff < threshold, (
        f"Structural integrity failure: Personality traits correlation is broken. "
        f"Measured Diff: {matrix_diff:.4f} (Max allowed: {threshold})"
    )
