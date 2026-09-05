"""
neuro_metrics.py

``NeuroMetrics`` -- rigidity, cognitive load, coherence (TF-IDF cosine similarity between
sentences), and self-focus (``self_focus_ext``, a narrower pronoun set than
:mod:`core.analysis.nlp_science`'s own ``self_focus``) over one response's text. Six of its seven
fields that overlap with ``nlp_science``'s own metrics are suffixed ``_ext`` for exactly that
reason -- see :meth:`~core.services.experiment_runner.ExperimentRunner._run_one`'s own docstring
for the merge-collision story this convention exists to avoid.
"""

from collections import Counter

import numpy as np
from nltk.tokenize import word_tokenize, sent_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Cap for cognitive_load's sentence-length normalization -- see NeuroMetrics.cognitive_load.
# 40 is a reasonable "very long sentence" threshold (typical English prose runs 15-20 words/
# sentence), not an empirically-derived one; documented as a chosen constant rather than a
# validated statistic, matching how abstract_ratio's own heuristic is disclosed below.
_COGNITIVE_LOAD_SENTENCE_LEN_CAP = 40


class NeuroMetrics:
    def __init__(self, sia):
        self.sia = sia

        self.self_pronouns = {"i", "me", "my", "mine", "myself"}
        self.modal_words = {"must", "should", "always", "never", "definitely"}
        self.abstract_words = {
            "meaning",
            "identity",
            "existence",
            "system",
            "process",
            "concept",
            "structure",
            "theory",
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
        """
        Composite of sentence length, punctuation density, and subordinate-clause rate.

        Notes
        -----
        Found during a wiki audit (``docs/source/wiki/04-llm-analytics.rst``) to have been an
        unweighted average of three quantities on incompatible raw scales: sentence length is a
        small positive integer (commonly 5-30+ words), while punctuation/subordinator density are
        already ratios in roughly ``[0, 1]``. Averaging them unnormalized let sentence length's raw
        magnitude dominate the composite, making the other two components nearly irrelevant to the
        final number. All three components are now min-max normalized to ``[0, 1]`` before
        averaging, so each contributes comparably. Sentence length is capped at
        ``_COGNITIVE_LOAD_SENTENCE_LEN_CAP`` words/sentence (a chosen "very long sentence"
        threshold, not an empirically-derived one -- disclosed the same way ``abstract_ratio``'s
        own heuristic is); punctuation density is clamped defensively, since a very short,
        heavily-punctuated response (e.g. ``"Wow!!!"``) can otherwise exceed 1.0 (more punctuation
        characters than words). Subordinator rate is already naturally bounded to ``[0, 1]`` (a
        count of matched words can never exceed the total word count), so it needs no clamp.

        This changes the metric's actual output values relative to the prior unnormalized version
        -- a deliberate, disclosed behavior change, not a bug fix that leaves values unchanged.
        """
        word_count = len(words)
        sent_count = len(sentences)

        if word_count == 0 or sent_count == 0:
            return 0

        avg_sentence_len = word_count / sent_count
        avg_sentence_len_norm = min(avg_sentence_len / _COGNITIVE_LOAD_SENTENCE_LEN_CAP, 1.0)

        punctuation_density = sum(1 for c in text if not c.isalnum() and not c.isspace()) / word_count
        punctuation_density_norm = min(punctuation_density, 1.0)

        sub_count = sum(1 for w in words if w in self.subordinators)
        sub_ratio = sub_count / word_count  # already in [0, 1]: sub_count can't exceed word_count

        return (avg_sentence_len_norm + punctuation_density_norm + sub_ratio) / 3

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
        except ValueError:
            # TfidfVectorizer raises ValueError on an empty vocabulary (e.g. every sentence is
            # entirely stopwords/punctuation) -- a real, expected degenerate-input case, not a bug.
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
            "coherence": 0,
        }
