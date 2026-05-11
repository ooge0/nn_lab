# 🧠 Psych Data Lab Pro: User Guide & FAQ

This application is a specialized benchmarking suite designed to quantify how Large Language Models (LLMs) adapt to psychological constraints under varying hyperparameters.

It combines:
- LLM behavior steering (Ollama / OpenAI)
- Synthetic psychotype generation
- NLP feature extraction (NLTK-based)
- Statistical and visual analysis (Streamlit + Plotly)

---

## 🛠️ Interface & Components

### 1. Lab Controls (Sidebar)

The sidebar defines the experimental engine configuration.

- **Temperature:** Controls randomness. Lower values (0.1–0.3) are deterministic; higher values (1.0+) increase creativity and instability.
- **Top P & Penalties:** Control token sampling and reduce repetition.
- **Random Seed:** Ensures reproducibility of experiments.

---

### 2. Automation Suite (Generation Tab)

Controls the Student–Teacher generation pipeline.

- **Self-Critic Mode:** Model evaluates its own output consistency.
- **Teacher Model:** External validator (e.g., Llama-3) used for scoring adherence.
- **Prompt Strategy:**
  - Expert Psychologist (Tuned)
  - Blind Mode (removes psychotype label for behavioral testing)
  - Raw (no system prompt baseline)
- **Active Sweep:** User single user option (one from many). Available options: None(using as single shot), Temperature, Top P , Freq Penalty, Presence Penalty
- When activated 'sweep parameter' mode the app allows select a dynamic mode ('Delta' or 'Min-max'), define number of steps, choose desc or asc for applying selected range. 

---

## 📊 Analytics & Evaluation Suite

The system evaluates LLM output across four layers:

---

## I. Structural & Lexical Metrics

### 1. Levenshtein Distance (Edit Distance)

$$
\text{lev}_{a,b}(i,j) = \min
\begin{cases}
\text{lev}(i-1,j)+1 \\
\text{lev}(i,j-1)+1 \\
\text{lev}(i-1,j-1)+1_{(a_i \neq b_j)}
\end{cases}
$$

Measures structural transformation between input and output.

---

### 2. Vocabulary Diversity (Unique Ratio)

$$
\text{Diversity} = \frac{\text{Unique Words}}{\text{Total Words}}
$$

Indicates lexical richness vs repetition.

---

### 3. Punctuation Density

$$
\text{Density} = \frac{\text{Punctuation Count}}{\text{Word Count}}
$$

Captures stylistic expression patterns across psychotypes.

---

## II. Semantic Behavior Metrics

### 4. Jaccard Similarity

$$
J(A,B) = \frac{|A \cap B|}{|A \cup B|}
$$

Measures semantic overlap between input and output.

---

### 5. Word Expansion Ratio

$$
\text{Expansion} = \frac{N_{out}}{N_{in}}
$$

Captures verbosity and narrative amplification.

---

### 6. Verification Heatmap

A grid showing % of successful psychotype adherence validated by the Teacher model.

---

## III. NLP Science Tab

This section introduces **psycholinguistic feature extraction using NLTK**.

It transforms raw generated text into measurable cognitive and stylistic signals.

---

### 🧪 1. POS Morphology Profile (Ternary Plot)

Breaks text into grammatical structure:

- Adjectives (ADJ)
- Nouns (NOUN)
- Verbs (VERB)

Used to identify stylistic fingerprints:
- High ADJ → expressive / emotional language
- High NOUN → object-centric / descriptive style
- High VERB → action-driven / dynamic style

---

### 🧠 2. Cognitive Complexity (Readability vs Diversity)

- **ARI (Automated Readability Index)**
- **Corrected TTR (lexical diversity)**

Used to measure:
- cognitive load
- abstraction level
- vocabulary richness

---

### 💬 3. Emotional Profile (Subjectivity vs Sentiment)

- **Subjectivity (TextBlob):** opinion vs fact orientation
- **Sentiment (VADER):** emotional polarity

Used to detect:
- expressive vs factual writing styles

---

### 📊 4. Emotional Stability (Sentiment Variance)

Measures variability of emotional tone across sentences:

- High variance → unstable / expressive / dramatic output
- Low variance → neutral / controlled output

---

### 🔁 5. Repetition & Fixation Score

Measures lexical repetition patterns:

- High score → fixation / constrained thinking
- Low score → flexible vocabulary usage

---

### 🧾 6. Sentence Structure Flow

Average sentence length distribution per psychotype:

- Short sentences → rigid / controlled
- Long sentences → narrative / expressive

---

## IV. Performance Metrics
### 🌌 Technical Brief: HDBSCAN Algorithm

**HDBSCAN** (Hierarchical Density-Based Spatial Clustering of Applications with Noise) is a clustering logic that finds groups based on how "crowded" (dense) the data points are. Unlike K-Means, it doesn't force every point into a cluster—if a point is in a lonely area, it is marked as **Noise**.

More technical details about ther algorithm you can find on [How HDBSCAN Works](https://hdbscan.readthedocs.io/en/latest/how_hdbscan_works.html) page or on [Hierarchical Density-Based Spatial Clustering of Applications with Noise (HDBSCAN)](https://www.geeksforgeeks.org/machine-learning/hdbscan/)

---

#### 1. The Core Logic: Mutual Reachability Distance
To find clusters, the algorithm calculates a special distance that penalizes points in low-density areas. This ensures that "noise" doesn't accidentally bridge two distinct clusters.

The distance between two points $a$ and $b$ is calculated as:

$$d_{mreach-k}(a, b) = \max \{core_k(a), core_k(b), d(a, b)\}$$

**Variables:**
*   $core_k(x)$: The distance to the $k$-th nearest neighbor (how "lonely" a point is).
*   $d(a, b)$: The standard physical (Euclidean) distance between the points.

---

#### 2. How it works (The "Hierarchy")
1.  **Transform Space:** It uses the formula above to spread out points in sparse regions.
2.  **Build a Tree:** It connects all points into a hierarchy (like a family tree) based on density.
3.  **Condense & Select:** It looks for "branches" that stay together for a long time as you increase the density threshold. These stable branches become your **Clusters**.

---

#### 3. Interpretation for LLM Experiments
In your project, this algorithm acts as a **Quality Filter**:

*   **Cluster ID > -1**: These points represent the "Typical" behavior of your models. They are the consistent linguistic patterns that define a Psychotype.
*   **Cluster ID = -1 (Noise)**: These are "Outliers." These generations are linguistically unique or weird compared to the rest. This usually happens when a model **hallucinates** or fails to maintain the requested psychotype traits.
*   **Density Mapping**: If "Cluster 0" is very tight, it means the models are extremely consistent for that specific Psychotype. If it is loose, the models are struggling to find a unified "voice."

---

**Summary for Non-Technical Users:**
Think of HDBSCAN as a party-goer. It looks for groups of people talking closely together. If someone is standing far away in the corner, HDBSCAN doesn't force them into a group—it simply labels them as "alone" (Noise). This helps you see the real, solid patterns in your data without the "static."


## V. Performance Metrics

### 7. Processing Velocity

$$
\text{Velocity} = \frac{\text{Time (ms)}}{\text{Word Count}}
$$

Efficiency of generation per token.

---

### 8. Latency

Total inference + validation time per generation.

---

## 📈 Scatter Plot Interpretation

### Semantic Overlap vs Expansion

- **Top-left:** creative expansion (low similarity, high verbosity)
- **Bottom-right:** conservative rewriting (high similarity, low verbosity)
- **Center:** balanced transformation

---

## ❓ FAQ

### Q: Why does verification show 0%?
A: Usually caused by high temperature or weak teacher model.

---

### Q: What is Blind Mode?
A: Removes psychotype label to test true behavioral generalization rather than keyword imitation.

---

### Q: What is the purpose of NLP Science tab?
A: It provides **interpretable linguistic features** (POS, sentiment, structure) to validate whether psychotypes emerge statistically, not just visually.

---

### Q: Can this be used outside psychology?
A: Yes. The same pipeline can model any behavioral dimension:
- formal vs informal writing
- technical vs creative style
- legal vs casual language

---

## 🧠 Summary

This system evaluates LLM behavior using:

- **Generation Layer:** controlled prompting
- **Evaluation Layer:** statistical + semantic metrics
- **NLP Science Layer:** interpretable linguistic structure

Together, they form a closed-loop experimental framework for analyzing language as behavioral data.