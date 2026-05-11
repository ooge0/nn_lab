# Psycho-Data-Augmentor

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
core/ data_contract.py                                      # contracts and data validation logic 
core/ neuro_metrics.py                                      # neuro_linguistic  analysis 
core/calculate_advanced_linguistic_metrics.py               # advanced linguistic metrics
results/{custom_file_name_for_specific_execution}.jsonl     # output dataset (JSONL format)
tests/                                                      # folder with tests
interfaces/                                                 # CLI and Web (Streamlit) entry points. (Will developed later)
```

### Core Pipeline
- Generate synthetic text via local LLM (Ollama)
- Apply psychotype transformation prompt
- Extract linguistic features using NLTK + TextBlob
- Store structured dataset (JSONL)
- Visualize results in Streamlit
---

## NLP Feature Set

- sentiment (VADER)
- subjectivity (TextBlob)
- lexical diversity (corrected TTR)
- readability (ARI)
- POS distribution
- self-focus ratio
- modality strength
- cognitive density
- repetition score
- sentiment variance
- abstractness ratio (WordNet heuristic)

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

## Notes

- App works on Windows 11 and Ubuntu
- Fully local via Ollama