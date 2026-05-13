import json
import random
import uuid
from datetime import datetime
from faker import Faker

fake = Faker()

# Psychotype definitions
PSYCHOTYPES = ["Baseline", "Epileptoid", "Hysteroid", "Schizoid", "Paranoid"]
BIASES = ["positive", "negative", "neutral", "toxic"]
MODELS = ["llama3:latest", "qwen:latest", "tinyllama:latest", "phi3:latest"]


# Step and reference counts
step_number = len(PSYCHOTYPES) * len(BIASES) * len(MODELS) * len(MODELS)
ETALON = len(MODELS) * len(MODELS)
max_total_tasks = 1200

# Constant: number of records to generate
NUM_RECORDS = 2000  # adjust this constant to control dataset size

# Model performance ranking (higher = faster)
MODEL_PERF = {
    "llama3:latest": 7,
    "qwen:latest": 6,
    "tinyllama:latest": 5,
    "phi3:latest": 3
}

# Base profiles for psychotypes (POS only ADJ, NOUN, VERB)
POS_PROFILES = {
    "Baseline":   {"ADJ": 0.30, "NOUN": 0.30, "VERB": 0.40},
    "Epileptoid": {"ADJ": 0.15, "NOUN": 0.35, "VERB": 0.50},
    "Hysteroid":  {"ADJ": 0.65, "NOUN": 0.20, "VERB": 0.15},
    "Schizoid":   {"ADJ": 0.20, "NOUN": 0.65, "VERB": 0.15},
    "Paranoid":   {"ADJ": 0.15, "NOUN": 0.20, "VERB": 0.65},
}


AVG_SENTENCE = {"Baseline": 11, "Epileptoid": 17, "Hysteroid": 9, "Schizoid": 21, "Paranoid": 14}

RIGIDITY = {
    "Baseline": 0.2,
    "Epileptoid": 0.8,
    "Hysteroid": 0.35,
    "Schizoid": 0.65,
    "Paranoid": 0.9,
}

SELF_FOCUS = {
    "Baseline": 0.15,
    "Epileptoid": 0.45,
    "Hysteroid": 0.85,
    "Schizoid": 0.55,
    "Paranoid": 0.75,}

COGNITIVE_LOAD = {"Baseline": 2.0, "Epileptoid": 3.5, "Hysteroid": 4.0, "Schizoid": 1.5, "Paranoid": 3.0}

# Bias adjustments for rigidity
bias_adjust = {"positive": -0.15, "neutral": 0.0, "negative": 0.1, "toxic": 0.25}
def jitter(value, sigma=0.05):
    """Gaussian jitter for tighter clusters"""
    return round(random.gauss(value, sigma), 3)

def generate_record(step: int, psychotype, bias, student, teacher):
    v_ok = random.random() > 0.1
    val = round(0.1 + (step / NUM_RECORDS) * (1.5 - 0.1), 3)

    # latency scaled by model performance
    base = 7000 / MODEL_PERF[student]
    duration_ms = round(random.gauss(base, base * 0.1), 3)
    if random.random() < 0.05:
        duration_ms = round(random.uniform(100, 7000), 3)

    # POS distribution anchored by psychotype
    pos_profile = POS_PROFILES[psychotype]
    pos_distribution = {k: jitter(v, 0.03) for k, v in pos_profile.items()}

    # Rigidity adjusted by bias
    rigidity_val = RIGIDITY[psychotype] + bias_adjust[bias]

    # --- NEW: lexical density calculation ---
    lexical_density = round(
        pos_distribution["ADJ"] + pos_distribution["NOUN"] + pos_distribution["VERB"], 3
    )

    record = {
        "experiment_id": "EXP2026-GOLDSET",
        "dataset_version": "v1.3",
        "id": str(uuid.uuid4()),
        "batch": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_tasks": NUM_RECORDS,
        "step": f"{step}/{NUM_RECORDS}",
        "psychotype": psychotype,
        "bias": bias,
        "student": student,
        "teacher": teacher,
        "output": fake.sentence(nb_words=10),
        "v_ok": v_ok,
        "v_ok_numeric": 1 if v_ok else 0,
        "val": val,
        "duration_ms": duration_ms,
        "word_count": random.randint(5, 500),
        "ms_per_word": round(duration_ms / max(1, random.randint(5, 20)), 2),
        "avg_sentence_length": AVG_SENTENCE[psychotype] + random.randint(-2, 2),
        "neuro_self_focus": jitter(SELF_FOCUS[psychotype], 0.05),
        "neuro_rigidity": jitter(rigidity_val, 0.05),
        "neuro_cognitive_load": jitter(COGNITIVE_LOAD[psychotype], 0.2),
        "cognitive_load": jitter(COGNITIVE_LOAD[psychotype], 0.2),
        "pos_distribution": pos_distribution,
        "neuro_coherence": jitter(0.5, 0.1),
        "neuro_modality": jitter(0.5, 0.1),
        "repetition_score": jitter(0.5, 0.1),
        "levenshtein_dist": random.randint(10, 200),
        "semantic_overlap": round(random.uniform(0, 1), 3),
        "expansion_ratio": round(random.uniform(0.5, 12), 3),
        "punc_density": round(random.uniform(0.01, 0.5), 3),
        "unique_ratio": round(random.uniform(0.3, 1.0), 3),
        "lexical_density": lexical_density,  # <-- added field
    }
    record["coherence"] = record["neuro_coherence"]
    record.update({
        "sentiment_variance": jitter(random.uniform(-0.3, 0.3), 0.05),
        "neuro_abstract_ratio_ext": jitter(random.uniform(-1, 1), 0.2),
        "readability_ari": random.uniform(0, 6),
        "corrected_ttr": jitter(random.uniform(-1, 1), 0.1),
        "corrected_iqr": jitter(random.uniform(-1, 1), 0.1),
    })

    return record


if __name__ == "__main__":
    output_file = "../results/dummy_gold.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for step in range(1, NUM_RECORDS + 1):
            psychotype = random.choice(PSYCHOTYPES)
            bias = random.choice(BIASES)
            student = random.choice(MODELS)
            teacher = random.choice(MODELS)
            rec = generate_record(step, psychotype, bias, student, teacher)
            f.write(json.dumps(rec) + "\n")
    print(f"✅ Generated {NUM_RECORDS} records into {output_file}")
