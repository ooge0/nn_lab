import json
import os
import random
from collections import Counter
from datetime import datetime
from types import SimpleNamespace

import numpy as np
from faker import Faker

fake = Faker()

# --- Archetype definitions ---
ARCHETYPES = ["Neutral", "Structured", "Expressive", "Detached", "Defensive"]
BIASES = ["positive", "negative", "neutral", "toxic"]
MODELS = ["llama3:latest", "qwen:latest", "tinyllama:latest", "phi3:latest", "mistral:7b-instruct-q4_K_M"]

NUM_RECORDS = 2000

MODEL_PERF = {
    "llama3:latest": 7,
    "qwen:latest": 6,
    "tinyllama:latest": 5,
    "phi3:latest": 3,
    "mistral:7b-instruct-q4_K_M": 9,
}

POS_PROFILES = {
    "Neutral": {"ADJ": 0.30, "NOUN": 0.30, "VERB": 0.40},
    "Structured": {"ADJ": 0.15, "NOUN": 0.35, "VERB": 0.50},
    "Expressive": {"ADJ": 0.65, "NOUN": 0.20, "VERB": 0.15},
    "Detached": {"ADJ": 0.20, "NOUN": 0.65, "VERB": 0.15},
    "Defensive": {"ADJ": 0.15, "NOUN": 0.20, "VERB": 0.65},
}

AVG_SENTENCE = {"Neutral": 11, "Structured": 17, "Expressive": 9, "Detached": 21, "Defensive": 14}
RIGIDITY = {"Neutral": 0.2, "Structured": 0.8, "Expressive": 0.35, "Detached": 0.65, "Defensive": 0.9}
STRATEGIES = {
    "Neutral": "Blind mode (Hide label)",
    "Structured": "Blind mode (Hide label)",
    "Expressive": "Behavioral conditioning (Tuned)",
    "Detached": "Raw / No system prompt",
    "Defensive": "Behavioral conditioning (Tuned)",
}


SELF_FOCUS = {"Neutral": 0.15, "Structured": 0.45, "Expressive": 0.85, "Detached": 0.55, "Defensive": 0.75}
COGNITIVE_LOAD = {"Neutral": 2.0, "Structured": 3.5, "Expressive": 4.0, "Detached": 1.5, "Defensive": 3.0}
bias_adjust = {"positive": -0.15, "neutral": 0.0, "negative": 0.1, "toxic": 0.25}

split_bias_mode = SimpleNamespace(random=random.choice([True, False]))
setattr(split_bias_mode, "True", True)
setattr(split_bias_mode, "False", False)


def jitter(value, sigma=0.05):
    return round(random.gauss(value, sigma), 3)


def compute_zipf_deviation(text, top_n=50):
    tokens = text.lower().split()
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


def generate_record(step, archetype, bias, student, teacher, sweep_mode="None"):
    v_ok = random.random() > 0.1

    # Updated: base_temp is now non-static, choosing a random float from 0.0 to 1.6
    base_temp = round(random.uniform(0.0, 1.6), 2)
    base_top_p, base_freq, base_pres = 0.9, 1.1, 0.2

    val = base_temp if sweep_mode == "None" else round(0.1 + (step / NUM_RECORDS) * (1.5 - 0.1), 2)
    base = 7000 / MODEL_PERF[student]
    duration_ms = round(random.gauss(base, base * 0.1), 3)

    pos_profile = POS_PROFILES[archetype]
    pos_distribution = {k: jitter(v, 0.03) for k, v in pos_profile.items()}
    pos_distribution["ADV"] = jitter(0.05, 0.01)

    rigidity_val = RIGIDITY[archetype] + bias_adjust[bias]
    lexical_density = round(sum(pos_distribution.values()), 3)

    strategy_str = STRATEGIES[archetype]
    archetype_about = f"About {archetype}: synthetic description placeholder."
    sys_prompt = f"Act as psychologist. Rewrite to the {archetype} archetype. Return JSON with 'text' key."
    output_text = fake.sentence(nb_words=15)

    return {
        "batch": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": NUM_RECORDS,
        "steps": step,
        "step": f"{step}/{NUM_RECORDS}",
        "strategy": strategy_str,
        "archetype": archetype,
        "archetype_about": archetype_about,
        "split_bias_mode": split_bias_mode.random,
        "bias": bias,
        "system_prompt": sys_prompt,
        "student": student,
        "teacher": teacher,
        "sweep_param": "Baseline" if sweep_mode == "None" else sweep_mode,
        "v_ok": v_ok,
        "v_ok_numeric": int(v_ok),
        "val": val,
        "val_temperature": base_temp,
        "val_top_p": base_top_p,
        "val_frequency_penalty": base_freq,
        "val_presence_penalty": base_pres,
        "output": output_text,
        "duration_ms": duration_ms,
        "validation_duration_ms": round(duration_ms * 0.35, 3),
        "rag_enabled": False,
        "rag_mode": None,
        "rag_top_k": None,
        "rag_query": "",
        "rag_chunks_count": 0,
        "rag_context_chars": 0,
        "rag_context": "",
        # metrics...
        "sentiment": jitter(random.uniform(-0.5, 0.5), 0.1),
        "sentiment_variance": jitter(random.uniform(0, 0.1), 0.01),
        "subjectivity": round(random.uniform(0.1, 0.9), 3),
        "lexical_density": lexical_density,
        "corrected_ttr": jitter(random.uniform(2.0, 5.0), 0.2),
        "readability_ari": round(random.uniform(5.0, 16.0), 2),
        "avg_sentence_length": float(AVG_SENTENCE[archetype] + random.randint(-2, 2)),
        "ms_per_word": round(duration_ms / max(1, random.randint(10, 40)), 2),
        "word_count": random.randint(15, 60),
        "self_focus": jitter(SELF_FOCUS[archetype], 0.05),
        "modality": jitter(0.1, 0.02),
        "cognitive_density": jitter(0.2, 0.05),
        "repetition_score": jitter(0.05, 0.01),
        "abstract_ratio": jitter(0.1, 0.02),
        "pos_distribution": pos_distribution,
        "rigidity": jitter(rigidity_val, 0.05),
        "sentiment_variance_ext": jitter(random.uniform(0, 0.1), 0.01),
        "abstract_ratio_ext": jitter(0.1, 0.02),
        "modality_ext": jitter(0.1, 0.02),
        "cognitive_load": jitter(COGNITIVE_LOAD[archetype], 0.2),
        "coherence": jitter(0.5, 0.1),
        "levenshtein_dist": random.randint(10, 300),
        "semantic_overlap": round(random.uniform(0, 1), 3),
        "expansion_ratio": round(random.uniform(5.0, 50.0), 2),
        "punc_density": round(random.uniform(0.01, 0.1), 3),
        "unique_ratio": round(random.uniform(0.5, 1.0), 3),
        "zipf_deviation": compute_zipf_deviation(output_text),
        # neuro fields
        "neuro_rigidity": jitter(rigidity_val, 0.05),
        "neuro_cognitive_load": jitter(COGNITIVE_LOAD[archetype], 0.2),
        "neuro_coherence": jitter(0.5, 0.1),
        "neuro_self_focus": jitter(SELF_FOCUS[archetype], 0.05),
        "neuro_abstract_ratio_ext": jitter(0.1, 0.02),
        "neuro_modality": jitter(0.1, 0.02),
        "pos_adj": pos_distribution["ADJ"],
        "pos_noun": pos_distribution["NOUN"],
        "pos_verb": pos_distribution["VERB"],
    }


# --- Cluster generator for HDBSCAN visualizations ---
def generate_cluster_dataset(
    num_records=2000, num_clusters=5, cluster_spread=0.5, noise_fraction=0.1, feature_dim=6, random_seed=42
):
    np.random.seed(random_seed)
    data, labels = [], []
    for cluster_id in range(num_clusters):
        center = np.random.uniform(-5, 5, size=feature_dim)
        points = center + cluster_spread * np.random.randn(
            int(num_records * (1 - noise_fraction) / num_clusters), feature_dim
        )
        data.append(points)
        labels.extend([cluster_id] * len(points))
    noise_points = np.random.uniform(-10, 10, size=(int(num_records * noise_fraction), feature_dim))
    data.append(noise_points)
    labels.extend([-1] * len(noise_points))
    data = np.vstack(data)
    labels = np.array(labels)


if __name__ == "__main__":
    single_teacher = True
    output_file = "../results/dummy_gold_clusters.jsonl"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for step in range(1, NUM_RECORDS + 1):
            archetype = random.choice(ARCHETYPES)
            bias = random.choice(BIASES)
            student = random.choice(MODELS)
            if single_teacher:
                teacher = MODELS[0]
            else:
                teacher = random.choice(MODELS)
            rec = generate_record(step, archetype, bias, student, teacher)
            f.write(json.dumps(rec) + "\n")
    print(f"✅ Generated {NUM_RECORDS} records into {output_file}")
