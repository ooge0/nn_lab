```markdown
# Psycho-Data-Augmentor

**Quick Summary – Psych Data Lab**
- App purpose: run AI/NLP models in different modes (Teacher–Student, Self‑Critic, Blind Mode) and collect structured results.
- Parameters: supports sweeps of temperature, top‑p, penalties, max tokens.
- RAG integration: retrieves knowledge chunks to enrich prompts.
- Analysis: calculates sentiment, subjectivity, lexical density, repetition, POS distribution, plus neuro‑metrics like rigidity, cognitive load, coherence, self‑focus.
- Visualization: PCA, HDBSCAN, UMAP clustering to compare model behavior and detect anomalies.
- Outcome: helps evaluate how models differ, what patterns they produce, and how parameters influence style and quality.

A tool for generating and analyzing synthetic psycholinguistic datasets using local LLMs (Ollama) and NLP feature extraction.

The system combines:
- LLM-based text generation (persona-driven rewriting)
- NLP-based feature extraction (NLTK / TextBlob)
- experimental psychotype modeling

---

## Supported Local Models (Ollama)

Recommended lightweight generative model:

- `qwen`
- `phi3`
- `tinyllama`
- `llama3`

---

## Installation

### 1. Create Environment (Python 3.12)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip  
```

```bash
pip install -r requirements.txt
```
---

### 3. PsychScientist and NeuroMetrics modules setup

```bash
python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('brown'); nltk.download('averaged_perceptron_tagger_eng')"
```
or 
```bash
python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab')"
````
---

## Running the Application

### Start Streamlit UI

```bash
streamlit run streamlit_app.py
```

---

### Start Ollama

```bash
ollama serve
```

Pull a model:
```bash
ollama pull llama3
```

Check models:
```bash
ollama list
```

---

## Project Structure
```
streamlit_app.py                                            # streamlit app file  
core/nlp_science.py                                         # psycholinguistic analysis (NLTK-based)  
core/data_contract.py                                       # contracts and data validation logic 
core/neuro_metrics.py                                       # neuro_linguistic analysis 
core/calculate_advanced_linguistic_metrics.py               # advanced linguistic metrics
results/{custom_file_name_for_specific_execution}.jsonl     # output dataset (JSONL format)
tests/                                                      # folder with tests
interfaces/                                                 # CLI and Web (Streamlit) entry points (planned)
```

### Core Pipeline
- Generate synthetic text via local LLM (Ollama)
- Apply psychotype transformation prompt
- Extract linguistic features using NLTK + TextBlob
- Store structured dataset (JSONL)
- Visualize results in Streamlit

---

## NLP Feature Set

- sentiment (VADER) → \[Sentiment = (Positive − Negative) / Total\]
- subjectivity (TextBlob) → \[Subjectivity = Subjective Words / Total Words\]
- lexical diversity (corrected TTR)
- readability (ARI)
- POS distribution
- self-focus ratio → \[SelfFocus = Self Pronouns / Total Pronouns\]
- modality strength
- cognitive density
- repetition score → \[Repetition = Repeated Tokens / Total Tokens\]
- sentiment variance
- abstractness ratio (WordNet heuristic)

---

## Neuro-Metrics

- rigidity → \[Rigidity = (Imperatives + Repetitions) / Total Sentences\]
- cognitive load → \[Cognitive Load = Complex Words / Total Words\]
- coherence (semantic similarity between sentences)
- anomaly detection (cluster outliers)

---

## Experimental Model

Psychotypes:
- Baseline → normal personality = control group
- Hysteroid → emotional, expressive, theatrical
- Paranoid → rigid, controlled, repetitive
- Schizoid → abstract, cognitive, low affect

---

## Hyperparameters

|Parameter|Effect|
|---|---|
|Temperature|creativity vs determinism|
|Top-p|token filtering|
|Frequency penalty|repetition control|
|Presence penalty|topic diversity|
|Max tokens|output length control|

---

## Recommended Setup

- Temperature: `0.3 – 1.2`
- Top-p: `0.9`
- Frequency penalty: `1.1 – 1.2`
- Seed: `42`
- Max Tokens: `800`
- Random seed: `42`

---

## OLLAMA MODEL DOWNLOAD MONITORING

### WINDOWS (PowerShell)

#### Pull model manually:
```bash
ollama pull mistral:7b
```

#### Show installed models:
```bash
ollama list
```

#### Stop current download:
CTRL + C

#### Check Ollama service:
```bash
Get-Process ollama
```
 
### LINUX / MACOS
#### Pull model manually:
```bash
ollama pull mistral:7b
```

#### Show installed models:
```bash
ollama list
```

#### Stop current download:
CTRL + C

#### Check running ollama processes:
```bash
ps aux | grep ollama
```

#### Kill stuck process:
```bash
pkill ollama
```

---

## Notes

- App works on Windows 11 and Ubuntu  
- Fully local via Ollama  
- Designed for model evaluation, psychotype transformation, and behavior analysis


### UMAP , HDBSCAN

```text
High-dimensional features
        ↓
StandardScaler
        ↓
UMAP projection
        ↓
HDBSCAN density graph
        ↓
Mutual reachability graph
        ↓
Minimum spanning tree
```