from collections import Counter

import numpy as np
from nltk.tokenize import word_tokenize, sent_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class NeuroMetrics:
    def __init__(self, sia):
        self.sia = sia

        self.self_pronouns = {"i", "me", "my", "mine", "myself"}
        self.modal_words = {"must", "should", "always", "never", "definitely"}
        self.abstract_words = {
            "meaning", "identity", "existence", "system",
            "process", "concept", "structure", "theory"
        }
        self.subordinators = {"because", "although", "which", "that", "who"}

    # -------------------------------
    # SAFE DIVISION
    # -------------------------------
    def _safe_div(self, a, b):
        return a / b if b > 0 else 0

    # -------------------------------
    # 1. SELF FOCUS
    # -------------------------------
    def self_focus(self, words):
        count = sum(1 for w in words if w in self.self_pronouns)
        return self._safe_div(count, len(words))

    # -------------------------------
    # 2. RIGIDITY
    # -------------------------------
    def rigidity(self, tokens):
        counts = Counter(tokens)
        repeated = sum(c for c in counts.values() if c > 1)
        return self._safe_div(repeated, len(tokens))

    # -------------------------------
    # 3. EMOTIONAL VOLATILITY
    # -------------------------------
    def emotional_variance(self, sentences):
        if len(sentences) < 2:
            return 0

        scores = [self.sia.polarity_scores(s)["compound"] for s in sentences]
        return float(np.var(scores))

    # -------------------------------
    # 4. ABSTRACTION
    # -------------------------------
    def abstraction(self, words):
        count = sum(1 for w in words if w in self.abstract_words)
        return self._safe_div(count, len(words))

    # -------------------------------
    # 5. MODALITY
    # -------------------------------
    def modality(self, words):
        count = sum(1 for w in words if w in self.modal_words)
        return self._safe_div(count, len(words))

    # -------------------------------
    # 6. COGNITIVE LOAD
    # -------------------------------
    def cognitive_load(self, words, sentences, text):
        word_count = len(words)
        sent_count = len(sentences)

        if word_count == 0 or sent_count == 0:
            return 0

        avg_sentence_len = word_count / sent_count

        punctuation_density = sum(
            1 for c in text if not c.isalnum() and not c.isspace()
        ) / word_count

        sub_count = sum(1 for w in words if w in self.subordinators)
        sub_ratio = sub_count / word_count

        return (avg_sentence_len + punctuation_density + sub_ratio) / 3

    # -------------------------------
    # 7. COHERENCE
    # -------------------------------
    def coherence(self, sentences):
        if len(sentences) < 2:
            return 0

        try:
            vectorizer = TfidfVectorizer()
            X = vectorizer.fit_transform(sentences)

            sims = []
            for i in range(len(sentences) - 1):
                sim = cosine_similarity(X[i], X[i + 1])[0][0]
                sims.append(sim)

            return float(np.mean(sims))
        except:
            return 0

    # -------------------------------
    # MAIN ENTRY
    # -------------------------------
    def compute(self, text):
        if not text or text == "EMPTY":
            return self._empty()

        tokens = word_tokenize(text.lower())
        words = [w for w in tokens if w.isalpha()]
        sentences = sent_tokenize(text)

        return {
            "self_focus": round(self.self_focus(words), 3),
            "rigidity": round(self.rigidity(tokens), 3),
            "sentiment_variance_ext": round(self.emotional_variance(sentences), 3),
            "abstract_ratio_ext": round(self.abstraction(words), 3),
            "modality_ext": round(self.modality(words), 3),
            "cognitive_load": round(self.cognitive_load(words, sentences, text), 3),
            "coherence": round(self.coherence(sentences), 3),

        }

    def _empty(self):
        return {
            "self_focus": 0,
            "rigidity": 0,
            "sentiment_variance_ext": 0,
            "abstract_ratio_ext": 0,
            "modality_ext": 0,
            "cognitive_load": 0,
            "coherence": 0
        }
