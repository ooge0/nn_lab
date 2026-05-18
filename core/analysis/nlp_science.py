from collections import Counter

import nltk
import numpy as np
from nltk.corpus import stopwords, wordnet
from nltk.sentiment import SentimentIntensityAnalyzer
from nltk.tokenize import word_tokenize, sent_tokenize
from textblob import TextBlob


class PsychScientist:
    def __init__(self):
        self.sia = SentimentIntensityAnalyzer()
        self.stop_words = set(stopwords.words('english'))

        # --- Psycholinguistic lexicons ---
        self.self_pronouns = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
        self.modal_verbs = {"must", "should", "need", "have", "ought", "shall", "may", "might", "could", "can", "would"}
        self.cognitive_verbs = {
            "think", "believe", "understand", "consider", "realize", "assume", "know", "analyze", "judge", "evaluate",
            "imagine", "remember", "predict", "decide"
        }

        # POS grouping
        self.pos_map = {
            "NOUN": ["NN", "NNS", "NNP", "NNPS"],
            "VERB": ["VB", "VBD", "VBG", "VBN", "VBP", "VBZ"],
            "ADJ": ["JJ", "JJR", "JJS"],
            "ADV": ["RB", "RBR", "RBS"]
        }

    def ensure_nltk(self):
        resources = [
            "punkt",
            "averaged_perceptron_tagger",
            "stopwords",
            "vader_lexicon",
            "wordnet",
            "omw-1.4"
        ]
        for r in resources:
            try:
                nltk.data.find(r)
            except:
                nltk.download(r)

    def zipf_deviation(self, text, top_n=100):
        tokens = word_tokenize(text.lower())
        words = [w for w in tokens if w.isalpha()]
        if not words:
            return 0.0

        freq = Counter(words)
        sorted_freq = sorted(freq.values(), reverse=True)
        ranks = np.arange(1, len(sorted_freq) + 1)

        C = sorted_freq[0]
        expected = np.array([C / r for r in ranks[:top_n]])
        observed = np.array(sorted_freq[:top_n])

        rmse = np.sqrt(np.mean((observed - expected) ** 2))
        norm_score = rmse / max(observed) if max(observed) > 0 else 0.0

        return norm_score

    def analyze_text(self, text: str, gen_dur: float = 0) -> dict:
        if not text or text == "EMPTY":
            return self._empty_result()

        # --- Tokenization ---
        tokens = word_tokenize(text.lower())
        words = [w for w in tokens if w.isalpha()]
        sentences = sent_tokenize(text)
        tagged = nltk.pos_tag(tokens)

        word_count = len(words)
        sent_count = max(1, len(sentences))

        if word_count == 0:
            return self._empty_result()

        # --- Sentiment ---
        sentiment = self.sia.polarity_scores(text)["compound"]
        sentence_sentiments = [self.sia.polarity_scores(s)["compound"] for s in sentences]
        sentiment_variance = float(np.var(sentence_sentiments)) if len(sentence_sentiments) > 1 else 0.0

        # --- POS Distribution (Grouped) ---
        pos_counts = Counter(tag for _, tag in tagged)
        total_pos = sum(pos_counts.values()) or 1
        pos_distribution = {}
        for group, tags in self.pos_map.items():
            count = sum(pos_counts[t] for t in tags if t in pos_counts)
            pos_distribution[group] = round(count / total_pos, 3)

        # --- Lexical Features ---
        unique_words = set(words)
        corrected_ttr = len(unique_words) / (2 * word_count) ** 0.5
        lexical_density = len([w for w in words if w not in self.stop_words]) / word_count

        # --- Subjectivity ---
        subjectivity = TextBlob(text).sentiment.subjectivity

        # --- Readability (ARI) ---
        char_count = len([c for c in text if c.isalnum()])
        ari = 4.71 * (char_count / word_count) + 0.5 * (word_count / sent_count) - 21.43

        # --- Psycholinguistic Features ---
        self_focus = sum(1 for w in words if w in self.self_pronouns) / word_count
        modality = sum(1 for w in words if w in self.modal_verbs) / word_count
        cognitive_density = sum(1 for w in words if w in self.cognitive_verbs) / word_count
        repetition_score = Counter(words).most_common(1)[0][1] / word_count

        # --- Abstract vs Concrete (WordNet heuristic) ---
        abstract_count, concrete_count = 0, 0
        for word in words:
            synsets = wordnet.synsets(word)
            if not synsets:
                continue
            hypernyms = synsets[0].hypernyms()
            if hypernyms:
                name = hypernyms[0].name()
                if "abstraction" in name or "entity" in name:
                    abstract_count += 1
                else:
                    concrete_count += 1
        total_ac = abstract_count + concrete_count
        abstract_ratio = abstract_count / total_ac if total_ac > 0 else 0

        # --- Structural Features ---
        avg_sentence_length = word_count / sent_count

        # --- Final Output ---
        return {
            "sentiment": round(sentiment, 3),
            "sentiment_variance": round(sentiment_variance, 3),
            "subjectivity": round(subjectivity, 3),
            "lexical_density": round(lexical_density, 3),
            "corrected_ttr": round(corrected_ttr, 3),
            "readability_ari": round(ari, 2),
            "avg_sentence_length": round(avg_sentence_length, 2),
            "ms_per_word": round(gen_dur / word_count, 4) if word_count > 0 else 0,
            "word_count": word_count,
            "self_focus": round(self_focus, 3),
            "modality": round(modality, 3),
            "cognitive_density": round(cognitive_density, 3),
            "repetition_score": round(repetition_score, 3),
            "abstract_ratio": round(abstract_ratio, 3),
            "pos_distribution": pos_distribution,
            "zipf_deviation": round(self.zipf_deviation(text), 4)
        }

        def _empty_result(self):
            return {
                "sentiment": 0,
                "sentiment_variance": 0,
                "subjectivity": 0,
                "lexical_density": 0,
                "corrected_ttr": 0,
                "readability_ari": 0,
                "avg_sentence_length": 0,
                "self_focus": 0,
                "modality": 0,
                "cognitive_density": 0,
                "repetition_score": 0,
                "abstract_ratio": 0,
                "pos_distribution": {},
                "zipf_deviation": 0.0
            }

    def _empty_result(self):
        return {
            "sentiment": 0,
            "sentiment_variance": 0,
            "subjectivity": 0,
            "lexical_density": 0,
            "corrected_ttr": 0,
            "readability_ari": 0,
            "avg_sentence_length": 0,
            "self_focus": 0,
            "modality": 0,
            "cognitive_density": 0,
            "repetition_score": 0,
            "abstract_ratio": 0,
            "pos_distribution": {},
            "zipf_deviation": 0.0
        }
