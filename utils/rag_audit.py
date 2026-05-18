"""
rag_audit.py

Utility script to validate RAG knowledge base quality.

Run:
    python utils/rag_audit.py
"""

from collections import Counter

from ai_projects_store.scr.NLP.psycho_data_augmentor.core.rag.ingestion import RAGEngine


def analyze_chunks(rag: RAGEngine):
    chunks = rag.store.chunks

    print("\n=== RAG AUDIT REPORT ===\n")

    # -------------------------
    # 1. BASIC STATS
    # -------------------------
    print(f"Total chunks: {len(chunks)}")

    archetype_counts = Counter([c.archetype for c in chunks])
    domain_counts = Counter([c.domain for c in chunks])

    print("\n-- Archetype distribution --")
    for k, v in archetype_counts.items():
        print(f"{k}: {v}")

    print("\n-- Domain distribution --")
    for k, v in domain_counts.items():
        print(f"{k}: {v}")

    # -------------------------
    # 2. EMPTY / BAD CHUNKS
    # -------------------------
    empty = [c for c in chunks if not c.content.strip()]
    too_short = [c for c in chunks if len(c.content) < 20]
    too_long = [c for c in chunks if len(c.content) > 400]

    print("\n-- Quality issues --")
    print(f"Empty chunks: {len(empty)}")
    print(f"Too short (<20 chars): {len(too_short)}")
    print(f"Too long (>400 chars): {len(too_long)}")

    # -------------------------
    # 3. DUPLICATES
    # -------------------------
    seen = set()
    duplicates = 0

    for c in chunks:
        key = (c.domain, c.content.strip().lower())
        if key in seen:
            duplicates += 1
        seen.add(key)

    print(f"Duplicate chunks: {duplicates}")

    # -------------------------
    # 4. SAMPLE OUTPUT
    # -------------------------
    print("\n-- Sample chunks --")
    for c in chunks[:5]:
        print(f"[{c.archetype} | {c.domain}] {c.content}")


def test_retrieval(rag: RAGEngine):
    print("\n=== RETRIEVAL SANITY TEST ===\n")

    queries = [
        "How does paranoid personality behave?",
        "How does schizoid person speak?",
        "What triggers hysteroid behavior?",
        "How does epileptoid think?"
    ]

    for q in queries:
        results = rag.query(q, k=3)

        print(f"\nQuery: {q}")

        for r in results:
            print(f" -> {r['archetype']} | {r['domain']} | {r['content'][:80]}")


if __name__ == "__main__":
    rag = RAGEngine()
    rag.load_knowledge_base("./knowledge")

    analyze_chunks(rag)
    test_retrieval(rag)