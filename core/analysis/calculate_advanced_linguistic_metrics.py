import Levenshtein


def calculate_advanced_linguistic_metrics(input_text, output_text, duration_ms):
    """
    Calculates technical NLP metrics to evaluate LLM transformation quality.
    """
    # Defensive programming: ensure we are working with strings
    input_text = str(input_text or "")
    output_text = str(output_text or "")

    input_words = set(input_text.lower().split())
    output_words = output_text.lower().split()
    output_set = set(output_words)

    word_count = len(output_words)
    input_count = len(input_words)

    # 1. Levenshtein Distance
    edit_dist = Levenshtein.distance(input_text, output_text)

    # 2. Jaccard Similarity (Semantic Overlap)
    intersection = input_words.intersection(output_set)
    union = input_words.union(output_set)
    jaccard_score = round(len(intersection) / len(union), 2) if union else 1.0

    # 3. Word Expansion Ratio
    expansion_ratio = round(word_count / max(1, input_count), 2)

    # 4. Processing Velocity (ms per word)
    # Using word_count defined above to avoid re-calculating len()
    ms_per_word = round(duration_ms / max(1, word_count), 2)

    # 5. Punctuation Density
    punc_count = sum(1 for char in output_text if char in ".,!?;:-")
    punc_density = round(punc_count / max(1, word_count), 2)

    # 6. Vocabulary Diversity
    unique_ratio = round(len(output_set) / max(1, word_count), 2)

    return {
        "levenshtein_dist": edit_dist,
        "semantic_overlap": jaccard_score,
        "expansion_ratio": expansion_ratio,
        "ms_per_word": ms_per_word,
        "punc_density": punc_density,
        "word_count": word_count,
        "unique_ratio": unique_ratio
    }