import os
import json
import random
from collections import Counter
from datetime import datetime
from types import SimpleNamespace

import numpy as np
from faker import Faker

fake = Faker()

# Psychotype definitions
PSYCHOTYPES = ["Baseline", "Epileptoid", "Hysteroid", "Schizoid", "Paranoid"]
BIASES = ["positive", "negative", "neutral", "toxic"]
MODELS = ["llama3:latest", "qwen:latest", "tinyllama:latest", "phi3:latest", "all-minilm:latest", "mistral:7b-instruct-q4_K_M"]


# Step and reference counts
step_number = len(PSYCHOTYPES) * len(BIASES) * len(MODELS) * len(MODELS)
ETALON = len(MODELS) * len(MODELS)
max_total_tasks = 1200

# Constant: number of records to generate
NUM_RECORDS = 2000

# Model performance ranking (higher = faster)
MODEL_PERF = {
    "llama3:latest": 7,
    "qwen:latest": 6,
    "tinyllama:latest": 5,
    "phi3:latest": 3,
    "all-minilm:latest": 4,
    "mistral:7b-instruct-q4_K_M": 9
}

# Base profiles for psychotypes (POS only ADJ, NOUN, VERB)
POS_PROFILES = {
    "Baseline": {"ADJ": 0.30, "NOUN": 0.30, "VERB": 0.40},
    "Epileptoid": {"ADJ": 0.15, "NOUN": 0.35, "VERB": 0.50},
    "Hysteroid": {"ADJ": 0.65, "NOUN": 0.20, "VERB": 0.15},
    "Schizoid": {"ADJ": 0.20, "NOUN": 0.65, "VERB": 0.15},
    "Paranoid": {"ADJ": 0.15, "NOUN": 0.20, "VERB": 0.65},
}

AVG_SENTENCE = {"Baseline": 11, "Epileptoid": 17, "Hysteroid": 9, "Schizoid": 21, "Paranoid": 14}
RIGIDITY = {
    "Baseline": 0.2,
    "Epileptoid": 0.8,
    "Hysteroid": 0.35,
    "Schizoid": 0.65,
    "Paranoid": 0.9,
}
# Added missing mapping dictionary to prevent crashes or missing assets
STRATEGIES = {
    "Baseline": "Direct Adaptation",
    "Epileptoid": "Structural Analyst",
    "Hysteroid": "Expert Psychologist (Tuned)",
    "Schizoid": "Abstract Conceptualizer",
    "Paranoid": "Systemic Evaluator"
}

SELF_FOCUS = {
    "Baseline": 0.15,
    "Epileptoid": 0.45,
    "Hysteroid": 0.85,
    "Schizoid": 0.55,
    "Paranoid": 0.75,
}
COGNITIVE_LOAD = {
    "Baseline": 2.0,
    "Epileptoid": 3.5,
    "Hysteroid": 4.0,
    "Schizoid": 1.5,
    "Paranoid": 3.0
}

# Bias adjustments for rigidity
bias_adjust = {"positive": -0.15, "neutral": 0.0, "negative": 0.1, "toxic": 0.25}

# Define the base choices
is_split = random.choice([True, False])

# Initialize with allowed variable names
split_bias_mode = SimpleNamespace(random=is_split)

# Force injection of reserved keywords as attributes
setattr(split_bias_mode, "True", True)
setattr(split_bias_mode, "False", False)


def jitter(value, sigma=0.05):
    """Gaussian jitter for tighter clusters"""
    return round(random.gauss(value, sigma), 3)


def compute_zipf_deviation(text, top_n=50):
    tokens = text.lower().split()  # simple tokenizer for synthetic data
    freq = Counter(tokens)
    if not freq:
        return 0.0

    sorted_freq = sorted(freq.values(), reverse=True)
    ranks = np.arange(1, len(sorted_freq) + 1)

    C = sorted_freq[0]
    expected = np.array([C / r for r in ranks[:top_n]])
    observed = np.array(sorted_freq[:top_n])

    rmse = np.sqrt(np.mean((observed - expected) ** 2))
    norm_score = rmse / max(observed) if max(observed) > 0 else 0.0
    return round(norm_score, 4)


def generate_record(step: int, psychotype, bias, student, teacher):
    v_ok = random.random() > 0.1
    val = round(0.1 + (step / NUM_RECORDS) * (1.5 - 0.1), 3)

    # Latency scaled by model performance
    base = 7000 / MODEL_PERF[student]
    duration_ms = round(random.gauss(base, base * 0.1), 3)
    if random.random() < 0.05:
        duration_ms = round(random.uniform(100, 7000), 3)

    # POS distribution anchored by psychotype
    pos_profile = POS_PROFILES[psychotype]
    pos_distribution = {k: jitter(v, 0.03) for k, v in pos_profile.items()}
    # Keep explicit track of ADV inside the structure if parsing depends on it
    pos_distribution["ADV"] = jitter(0.05, 0.01)

    # Rigidity adjusted by bias
    rigidity_val = RIGIDITY[psychotype] + bias_adjust[bias]

    # Lexical density calculation
    lexical_density = round(
        pos_distribution["ADJ"] + pos_distribution["NOUN"] + pos_distribution["VERB"], 3
    )

    # Generate missing metadata matching working structure
    strategy_str = STRATEGIES[psychotype]
    sys_prompt = f"Act as psychologist. Rewrite to the {psychotype} psychotype. Return JSON with 'text' key."
    output_text = fake.sentence(nb_words=15)

    record = {
        "batch": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": NUM_RECORDS,
        "steps": 1,
        "step": f"{step}/{NUM_RECORDS}",
        "strategy": strategy_str,
        "psychotype": psychotype,
        "split_bias_mode": split_bias_mode.random,
        "bias": bias,
        "system_prompt": sys_prompt,
        "student": student,
        "teacher": teacher,
        "sweet_param": random.choice(["Temperature", "Top_P", "Top_K"]),
        "v_ok": v_ok,
        "v_ok_numeric": 1 if v_ok else 0,
        "val": val,
        "output": fake.sentence(nb_words=15),
        "duration_ms": duration_ms,
        "validation_duration_ms": round(duration_ms * 0.35, 3),  # FIXED
        "rag_enabled": False,  # FIXED
        "rag_mode": None,  # FIXED
        "rag_top_k": None,  # FIXED
        "rag_query": "",  # FIXED
        "rag_chunks_count": 0,  # FIXED
        "rag_context_chars": 0,  # FIXED
        "rag_context": "",  # FIXED
        "sentiment": jitter(random.uniform(-0.5, 0.5), 0.1),  # FIXED
        "sentiment_variance": jitter(random.uniform(0, 0.1), 0.01),
        "subjectivity": round(random.uniform(0.1, 0.9), 3),  # FIXED
        "lexical_density": lexical_density,
        "corrected_ttr": jitter(random.uniform(2.0, 5.0), 0.2),
        "readability_ari": round(random.uniform(5.0, 16.0), 2),
        "avg_sentence_length": float(AVG_SENTENCE[psychotype] + random.randint(-2, 2)),
        "ms_per_word": round(duration_ms / max(1, random.randint(10, 40)), 2),
        "word_count": random.randint(15, 60),
        "self_focus": jitter(SELF_FOCUS[psychotype], 0.05),
        "modality": jitter(0.1, 0.02),
        "cognitive_density": jitter(0.2, 0.05),
        "repetition_score": jitter(0.05, 0.01),
        "abstract_ratio": jitter(0.1, 0.02),
        "pos_distribution": pos_distribution,
        "rigidity": jitter(rigidity_val, 0.05),
        "sentiment_variance_ext": jitter(random.uniform(0, 0.1), 0.01),
        "abstract_ratio_ext": jitter(0.1, 0.02),
        "modality_ext": jitter(0.1, 0.02),
        "cognitive_load": jitter(COGNITIVE_LOAD[psychotype], 0.2),
        "coherence": jitter(0.5, 0.1),
        "levenshtein_dist": random.randint(10, 300),
        "semantic_overlap": round(random.uniform(0, 1), 3),
        "expansion_ratio": round(random.uniform(5.0, 50.0), 2),
        "punc_density": round(random.uniform(0.01, 0.1), 3),
        "unique_ratio": round(random.uniform(0.5, 1.0), 3)
    }
    record["zipf_deviation"] = compute_zipf_deviation(output_text)
    return record


if __name__ == "__main__":
    single_teacher = True
    output_file = "../results/dummy_gold.jsonl"


    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for step in range(1, NUM_RECORDS + 1):
            psychotype = random.choice(PSYCHOTYPES)
            bias = random.choice(BIASES)
            student = random.choice(MODELS)
            if 'single_teacher':
                    teacher = MODELS[0]
            else:
                teacher = random.choice(MODELS)
            rec = generate_record(step, psychotype, bias, student, teacher)
            f.write(json.dumps(rec) + "\n")
    print(f"✅ Generated {NUM_RECORDS} records into {output_file}")
