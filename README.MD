# LLM data lab / Psycho-Data-Augmentor

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

## Dependency Architecture

To prevent heavy CUDA, Triton, and NCCL dependency conflicts between Windows and Linux, this project implements a split compilation structure powered by `pip-tools`.

*   `requirements.in`: Single source-of-truth for your top-level project dependencies.
*   `requirements-base.txt`: Compiled core cross-platform packages (Streamlit, Pandas, Scikit-Learn, OpenAI, etc.).
*   `requirements-linux.txt`: Compiled Ubuntu-only packages (`triton`, `nvidia-nccl-cu13`, `nvidia-nvshmem-cu13`).
*   `requirements-windows.txt`: Reserved for Windows-specific constraints (remains empty by default as Windows installs PyTorch via a custom index URL).

---
## Deployment and Operations Architecture

The repository enforces a strict boundary between Isolated Validation (`tox`) and Local Application Runtime (`.venv`):

```text
               [ Master requirements.in ]
                           │
             ┌─────────────┴─────────────┐
      (pip-compile)               (pip-compile)
             ▼                           ▼
[ requirements-base.txt ]    [ requirements-linux.txt ]
             │                           │
   ┌_________┴_________┐       ┌_________┴_________┐
   ▼                   ▼       ▼                   ▼
Development         Testing    Development         Testing
(`.venv` App Run)   (`tox` CI) (`.venv` App Run)   (`tox` CI)
   │                   │       │                   │
   ▼                   ▼       ▼                   ▼
 [win11 host]     [.tox sandbox] [ubuntu host]   [.tox sandbox]
```

---
## Installation & Setup

### 1. Pre-install Core Management Tools (One-time)
Install management packages globally/at the user level to ensure CLI compilation binaries are available outside project virtual environments.

**Ubuntu Setup**
```bash
sudo apt update && sudo apt install pipx python3-venv -y
pipx install tox
pipx install pip-tools
```

**Windows 11 Setup**
Open Command Prompt or PowerShell (Do **not** activate a local project `.venv`):
```cmd
python -m pip install --user tox pip-tools
```

### 2. Create the Local Virtual Environment
Isolated local environments are used exclusively for developing and running the interface app.

**Ubuntu:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows 11:**
Until PyTorch has no stable version for Python 3.14, the Python 3.12 is stable for the current project(updated 9 June 2026)  
```cmd
py -3.12 -m venv .venv
.venv\Scripts\activate
```

*Note: Always verify `.venv/` and `.tox/` are included in your `.gitignore` to prevent host environment corruption across your Git tracking branch.*

### 3. Generate Dependencies (`pip-tools` compilation)
When updating top-level libraries inside `requirements.in`, avoid blind `pip-compile` execution. Generate explicit platform splits instead:

- Generate Cross-Platform base packages (Can run on Windows or Ubuntu)
```bash
pip-compile requirements.in --output-file=requirements-base.txt
```
- Generate Linux Platform Stack (Must be executed on Ubuntu)
```bash
pip-compile requirements.in --output-file=requirements-linux.txt
```

### 4. Install Dependencies

**On Ubuntu:**
```bash
pip install --upgrade pip  
pip install -r requirements-base.txt -r requirements-linux.txt
```

**On Windows 11:**
Windows requires targeted PyTorch builds from their official index registry to circumvent standard Linux binary drops.
```cmd
python -m pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --no-cache-dir
pip install -r requirements-base.txt
```

---

## Phase 1: Verification and Automated Isolation (`tox`)

You do not need to manually configure, update, or sync target environments to test execution. 
`tox` abstracts environment construction entirely. It queries the local host system (`win32` vs `linux`), sets up a hidden sandbox directory inside `.tox/`, pulls down the correct architectural dependencies automatically, and tests your logic.

**When to use it:** Run this when checking out a new feature, editing core modules, or preparing a Git commit to ensure you did not introduce environment breaks between Windows 11 and Ubuntu.

From your repository root, simply execute:
```bash
tox
```
*   **On Ubuntu:** Tox hooks `requirements-base.txt` + `requirements-linux.txt` then boots `pytest`.
*   **On Windows 11:** Tox installs `requirements-base.txt`, runs the native Windows CUDA wheel installation directly from the PyTorch index, skips Linux binaries, then boots `pytest`.
---

=============== PHASE II ===========================

## Phase 2: Running the Application Core

Runs your local text processing layers, loads the local neural network weights via Ollama, builds NLP corpora data matrices, and fires up the interactive Streamlit dashboard. This executes natively inside your persistent local `.venv` profile to support instant code hot-reloading. Do not use `tox` to run the active Streamlit app.

### 1. Fire up background Model Servers (Separate terminal tab)
```bash
ollama serve
ollama pull llama3
```

### 2. Boot the UI Layer using automated wrappers

**On Windows 11 (run.bat):**
Create a file named `run.bat` in the project root folder. Execute this pre-packaged script inside your active, activated command line:
```cmd
run
```

**On Ubuntu Linux (Makefile):**
Create a file named `Makefile` in the project root folder. Execute the build rule target block:
```bash
make run
```

---

## PsychScientist and NeuroMetrics Modules Setup

Run the following initialization layer to populate required NLTK tokenization Corpora:
```bash
python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('brown'); nltk.download('averaged_perceptron_tagger_eng')"
```
or 
```bash
python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab')"
```

---

## Supported Local Models (Ollama)

Recommended lightweight generative models:
- `qwen`
- `phi3`
- `tinyllama`
- `llama3`

---

## Neo4j setup for knowledge graph implementation

The Knowledge Graph module uses Neo4j to store relationships between archetypes, biases, and evaluation artifacts. If Neo4j is not configured, the rest of the application will continue to function normally.

### 1. Install Neo4j Community Edition

Download Neo4j Community Edition from the official website and extract/install it according to your operating system.

### Windows 11

1. Download the Neo4j Community ZIP package.
2. Extract it to a location such as:

```text
D:\setup\neo4j\2026.05.0\
```

3. Open PowerShell:

```powershell
cd D:\setup\neo4j\2026.05.0\bin
neo4j console
```

4. Wait until the server reports:

```text
Bolt enabled on localhost:7687
HTTP enabled on localhost:7474
```

5. Open the Neo4j Browser:

```text
http://localhost:7474
```

6. Log in with the default credentials:

```text
Username: neo4j
Password: neo4j
```

7. Set a new password when prompted.

---

### Ubuntu / Linux

Install Java if it is not already present:

```bash
sudo apt update
sudo apt install openjdk-21-jre -y
```

Download and extract Neo4j Community Edition:

```bash
tar -xzf neo4j-community-*.tar.gz
cd neo4j-community-*/bin
```

Start Neo4j:

```bash
./neo4j console
```

Open the Neo4j Browser:

```text
http://localhost:7474
```

Log in using:

```text
Username: neo4j
Password: neo4j
```

and create a new password.

---

### 2. Configure Application Credentials

Create the file:

```text
config/config.ini
```

Example:

```ini
[neo4j]
uri = bolt://localhost:7687
user = neo4j
password = your_password_here
```

For security reasons, `config.ini` should not be committed to source control.

---

### 3. Verify Connectivity

Before running the application, verify the connection:

a. Use Neo4j web console

```APOC
CALL apoc.help('pageRank');
```
Result should be ``
or
b. Pythoin script
```python
from py2neo import Graph

graph = Graph(
    "bolt://localhost:7687",
    auth=("neo4j", "your_password_here")
)

print(graph.run("RETURN 1 AS test").data())
```

Expected output:

```python
[{'test': 1}]
```

---

### 4. Troubleshooting

If the application reports:

```text
ConnectionUnavailable:
Cannot open connection to bolt://localhost:7687
```

verify that Neo4j is running.

Windows:

```powershell
netstat -ano | findstr 7687
```

Linux:

```bash
ss -tlnp | grep 7687
```

Expected result:

```text
LISTEN
```

which indicates that the Bolt protocol endpoint is available and accepting connections.


================================
================================
================================
================================

### Start Ollama (mandatory action)
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

## Running the Streamlit application

### Start Streamlit UI
```bash
streamlit run streamlit_app.py
```
---

## Project Structure
```text
streamlit_app.py                                            # Streamlit main web app interface
core/data_contract.py                                       # Contracts and data validation logic 
core/neuro_metrics.py                                       # Neuro-linguistic feature analysis engine
core/nlp_science.py                                         # Psycholinguistic analysis processing (NLTK-based)  
core/calculate_advanced_linguistic_metrics.py               # Advanced statistical linguistic aggregations
requirements.in                                             # Master top-level dependency declaration file
requirements-base.txt                                       # Compiled platform-agnostic dependencies
requirements-linux.txt                                      # Compiled Ubuntu specific system dependencies
tox.ini                                                     # Cross-platform automated test matrix configuration
results/{custom_file_name_for_specific_execution}.jsonl     # Structured pipeline output datasets (JSONL format)
tests/                                                      # Unit test suites folder
interfaces/                                                 # CLI and Web entry-point layout modules (planned)
```

### Core Pipeline
1. Generate synthetic text via local LLM (Ollama)
2. Apply psychotype transformation prompt
3. Extract linguistic features using NLTK + TextBlob
4. Store structured dataset (JSONL)
5. Visualize results in Streamlit

---

## NLP Feature Set

- sentiment (VADER) → `[Sentiment = (Positive − Negative) / Total]`
- subjectivity (TextBlob) → `[Subjectivity = Subjective Words / Total Words]`
- lexical diversity (corrected TTR)
- readability (ARI)
- POS distribution
- self-focus ratio → `[SelfFocus = Self Pronouns / Total Pronouns]`
- modality strength
- cognitive density
- repetition score → `[Repetition = Repeated Tokens / Total Tokens]`
- sentiment variance
- abstractness ratio (WordNet heuristic)

---

## Neuro-Metrics

- rigidity → `[Rigidity = (Imperatives + Repetitions) / Total Sentences]`
- cognitive load → `[Cognitive Load = Complex Words / Total Words]`
- coherence (semantic similarity between sentences)
- anomaly detection (cluster outliers)

---

## Experimental Model

Archetypes:
- Common →  strict formatting, structural wrapper, zero filtering. 
- Neutral → normal personality = control group
- Expressive → emotional, expressive, theatrical
- Defensive → rigid, controlled, repetitive
- Detached → abstract, cognitive, low affect

---

## Hyperparameters

| Parameter | Effect |
| --- | --- |
| Temperature | creativity vs determinism |
| Top-p | token filtering |
| Frequency penalty | repetition control |
| Presence penalty | topic diversity |
| Max tokens | output length control |

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
```powershell
ollama pull mistral:7b
```

#### Show installed models:
```powershell
ollama list
```

#### Stop current download:
`CTRL + C`

#### Check Ollama service:
```powershell
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
`CTRL + C`

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

- App works seamlessly across Windows 11 and Ubuntu environments.
- Fully local operation utilizing local Ollama configurations.
- Designed strictly for model evaluation, psychotype transformation pipelines, and behavioral feature tracking.

### UMAP, HDBSCAN Pipeline Flow
```text
High-dimensional features↓StandardScaler
        ↓
UMAP projection
        ↓
HDBSCAN density graph
        ↓
Mutual reachability graph↓Minimum spanning tree
```