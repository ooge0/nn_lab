This program is a specialized benchmarking suite designed for the quantitative assessment of how Large Language Models (LLMs) adapt to psychological constraints under various hyperparameters. It allows researchers to systematically vary generation parameters and observe how this affects the cognitive, semantic, and stylistic characteristics of the text. Thus, the tool provides not only performance measurement but also an in-depth analysis of model behavior in the context of psycholinguistics.

It combines:
- LLM text generation (Ollama / local models), providing controlled experiments with different architectures.
- Psycholinguistic analysis (NLTK / TextBlob), which allows for evaluating emotionality, cognitive load, and linguistic patterns.
- Statistical assessment of model behavior, including metrics of consistency, repeatability, and semantic overlap.
- Visualization (Streamlit + Plotly), which provides interactive charts, heatmaps, and clustering for result interpretation.

This suite creates a unified research environment where experiments, analysis, and real-time monitoring can be combined, making it useful for both academic research and applied model optimization tasks.

## 🛠️ Interface and Components

### Sidebar (Lab Controls + Debug/Recovery)
The sidebar is the main control block for the experiment:

- **Toggle Debug/Lab** Switch between debug and laboratory experiment modes.  

- **Debug Preset** - *Modules*: active modules (**Ollama**, **NLP**) with status indicators.  
  - *Modes*: **SC (Self‑Critic)**, **T‑S (Teacher–Student)**.  

- **Lab Controls (Baseline Parameters)** Panel for configuring static hyperparameters: 
    - **Temperature** — controls the level of randomness in the response. Low values → more predictable and logical texts; high values → creative but less stable.
    - **Top P** — determines which tokens are considered when choosing the next word (filtering by probability). A smaller value → more controlled output.
    - **Frequency Penalty** — reduces the likelihood of reusing the same words or phrases.
    - **Presence Penalty** — encourages the appearance of new topics or words to avoid monotony.
    - **Max Tokens** — limits the maximum response length (number of generated tokens).
    - **Random Seed** — sets the initial value for the randomness generator, allowing for the reproduction of the same results with identical settings.

  Buttons:  
    - **Save JSONL** — saving experiment results to a file  
    - **Clear History** — clearing the run history  

- **Experiment Recovery** - Loading previous experiments (e.g., `lab_ex...85042.jsonl`)  
  - **Inject Data** — reusing data in a new run or loading previously generated data 
---

### 🚀 Generation

This section describes the generation and model interaction mechanisms:

- **Model Interaction Modes:** - *Student–Teacher* — the student model learns from examples of the teacher model.  
  - *Self‑Critic* — the model evaluates its own output without an external teacher.  
  - *Single Shot* — one-time generation without additional iterations.  

- **Experiment Hyperparameter Setup Modes:** - *None* — static parameters are taken from the *Baseline Parameters* tab.  
  - *Sweep Mode* — dynamic hyperparameter range, which can be set via:  
    - **Delta** — changing the parameter by a fixed step.  
    - **Min‑Max** — generation within a specified range.  

- **Sweep‑experiments** Performed for parameters: Temperature, Top P, Frequency Penalty, Presence Penalty.  
  Formally:  
  $$
  Sweep(Parameter) = \{p_{min}, p_{min} + \Delta, \dots, p_{max}\}
  $$

- **Prompt Strategies:** - *Expert Psychologist* — strategy with an emphasis on psycholinguistic features.  
  - *Blind Mode* — without explicit psychotype designation.  
  - *Raw baseline* — basic prompt without additional modifications.  

- **RAG (Retrieval Augmented Generation):** Support for modes: *Psychotype Only* and *Full Context*.  
  The Top‑K parameter determines the number of relevant documents to load:  
  $$
  Context = \{d_1, d_2, \dots, d_K\}
  $$

- **Bias split function:** Allows for separating the influence of systemic and user biases in generation.

- **Text generation for different psychotypes:** Baseline, Hysteroid, Paranoid, Schizoid.  

- **Experiment progress display:** - During generation, the experiment execution status is displayed.  
  - Upon completion, results are saved in JSONL format with timestamps and statuses (**OK / Fail**) manually if needed.  

---

### 📊 Performance

This section describes model performance and latency metrics:

- **Speed and Latency Metrics** Measure the efficiency of text generation and validation.

- **Velocity (generation speed):** Formula for calculating the average time per word:  
  $$
  Velocity = \frac{Time\ (ms)}{Word\ Count}
  $$

- **Total Generation + Validation Time** Includes the total time spent creating the text and its verification.

- **Summary for each experiment:** - Records (number of records)  
  - Steps (number of steps)  
  - Sweep Parameter (the variable parameter)  
  - Value Range (range of values)  
  - Avg. ms/word (average time per word)  
  - Avg. Validation Time (average validation time)

- **Raw experiment logs** Display of the experiment result in tabular form.  

---

### 📈 Analytics

This section describes tools for analyzing the style and quality of generations:

- **Scatter Plot: Semantic Overlap vs Expansion** Used to visualize the relationship between semantic overlap and text expansion.  
  Formally:  
  $$
  Overlap = \frac{|Tokens_{gen} \cap Tokens_{ref}|}{|Tokens_{ref}|}
  $$
  $$
  Expansion = \frac{|Tokens_{gen}|}{|Tokens_{ref}|}
  $$

- **Scatter Plot Interpretation:** - Top Left Corner → creative expansion (low overlap, high expansion)  
  - Bottom Right Corner → conservative paraphrasing (high overlap, low expansion)  
  - Center → balanced transformation  

- **Visualization of hyperparameter influence on style and quality** Study of the dependency between Temperature, Top P, Penalties, and text characteristics.  
  For example:  
  $$
  Style\ Shift = f(Temperature, TopP, Penalties)
  $$

- **Verification Success Heatmap** Shows the percentage of successful generations for different parameter combinations:  
  $$
  Success\ Rate = \frac{Valid\ Generations}{Total\ Generations} \cdot 100\%
  $$

---

### 🧪 NLP Science
#### POS Morphology Profile
Part-of-speech distribution:
  - ADJ (adjectives)
  - NOUN (nouns)
  - VERB (verbs)

**Interpretation:**
  - more ADJ → emotional, descriptive style
  - more NOUN → object-oriented style
  - more VERB → dynamic, active style

#### Cognitive Complexity: ARI + TTR (Readability vs Diversity)  
$$
Cognitive\ Load = \frac{Complex\ words}{Total\ number\ of\ words}
$$

- ARI (readability index)
- corrected TTR (lexical diversity)

**Purpose:** measuring the level of abstraction and cognitive load.

#### Emotional Profile: (Subjectivity vs Sentiment) 
$$
Subjectivity = \frac{Subjective\ words}{Total\ number\ of\ words}
$$  

$$
Sentiment = \frac{Positive - Negative}{Total}
$$

- Subjectivity (TextBlob)
- Sentiment (VADER)

**Purpose:** determining the emotionality and objectivity of the text.


#### Emotional Stability (Sentiment Variance)
Measures the fluctuation of emotional tone between sentences.
- high variability → dramatic / unstable style
- low → stable / neutral style

#### Repetition Score
$$
Repetition = \frac{Repeated\ tokens}{Total\ number\ of\ tokens}
$$

Evaluates the frequency of repeating words and structures.
- high value → fixation / limited thinking
- low value → flexible vocabulary

#### Sentence Structure  
$$
Rigidity = \frac{Imperatives + Repetitions}{Total\ Sentences}
$$

Average sentence length for each psychotype.
- short sentences → control / rigidity
- long sentences → narrativity / expressiveness

#### Self-focus Index  
$$
SelfFocus = \frac{Self\ Pronouns}{Total\ Pronouns}
$$


#### Processing Speed
$$
\text{Velocity} = \frac{\text{Time (ms)}}{\text{Word Count}}
$$

#### Latency
Total generation and response validation time.

---

#### 📈 Scatter Plot Interpretation (Overlap vs Expansion)

- **Top Left Corner:** creative expansion
- **Bottom Right Corner:** conservative paraphrasing
- **Center:** balanced content transformation

---

### 🧩 Clustering

- **Advanced Density Clustering (UMAP + HDBSCAN)** Used for latent space analysis and identifying structures in data.  
  - **UMAP** — Uniform Manifold Approximation and Projection. Dimensionality reduction preserving local and global structure.  
  - **HDBSCAN** — density-based clustering with automatic noise determination.
    References:
    - HDBSCAN: 
      - [How HDBSCAN Works](https://hdbscan.readthedocs.io/en/latest/how_hdbscan_works.html)
      - UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction (2018) 
        - PDF: https://arxiv.org/pdf/1802.03426
      - Shapley-based explainable AI for clustering applications in fault diagnosis and prognosis
        - DOI:10.1007/s10845-024-02468-2
      - Unsupervised Learning: Comparative Analysis of Clustering Techniques on High-Dimensional Data
        - PDF: https://arxiv.org/html/2503.23215v1
      - The Information Geometry of UMAP
        - PDF: https://hal.science/hal-04819511v1/file/umap_information_geometry.pdf
      - Dim Reduction & Vis. Advanced Data Visualization. CS 6965. Fall 2019. Prof. Bei Wang Phillips University of Utah
        - https://www.sci.utah.edu/~beiwang/teaching/cs6965-fall-2019/Lecture02-DR.pdf
      - Clustering, Regression and Vis. Advanced Data Visualization. CS 6965. Fall 2019. Prof. Bei Wang Phillips University of Utah
        - https://www.sci.utah.edu/~beiwang/teaching/cs6965-fall-2019/Lecture06-Clustering.pdf



- **Parameters:** - *Min Cluster Size* — minimum number of points in a cluster.  
  - *Min Samples* — minimum number of neighbors to determine density.  
  - *Neighbors* — number of neighbors for building the graph in UMAP.  
  - *Min Distance* — minimum distance between points in the projection.

- **Latent Space Analysis + Minimum Spanning Tree (MST)** Used to visualize paths between clusters and analyze their topology.

- **Clustering Quality Indices:** 
  - **CPI (Silhouette):** 

$$
s(i) = \frac{b(i) - a(i)}{\max\{a(i), b(i)\}}
$$

  where $$a(i)$$ is the average distance to points in its cluster, $$b(i)$$ is the minimum average distance to another cluster.  

  - **RMSEA (DBI – Davies–Bouldin Index):** 

$$
DBI = \frac{1}{k} \sum_{i=1}^{k} \max_{j \neq i} \frac{\sigma_i + \sigma_j}{d(c_i, c_j)}
$$

  where $$\sigma_i$$ is the average deviation in cluster $$i$$, $$d(c_i, c_j)$$ is the distance between centroids.  

  - **ARI (Adjusted Rand Index):** 
$$
ARI = \frac{RI - E[RI]}{\max(RI) - E[RI]}
$$

  where $$RI$$ is the Rand Index, measuring the consistency of clustering with baseline labels.

- **Behavioral Anomaly Analysis** Identification of outliers (anomalous generations) that do not match expected psychotypes.  
  - Outlier percentage:  

$$
Outlier\ Rate = \frac{N_{outliers}}{N_{total}} \cdot 100\%
$$

  - Examples of texts from clusters and noise points.

- **Noise Detection** Generations that do not match the psychotype are automatically marked as *Noise* and excluded from the main analysis.


---

### 🧬 Model Evaluation

This section contains information on the comprehensive evaluation of models:

- **Metric evaluation (linguistic / neuro)** for predicting target labels:  
  - hallucination  
  - truthful output  
  - anomaly  
  - psychotype  

- **Dropdown for selecting target column** Allows choosing the target column for prediction.  

- **Test Size (train/test split)** Determines the proportion of data for training and testing:  
  $$
  Train\ Size + Test\ Size = 1
  $$

- **Evaluation Metrics:** - Accuracy:  
  $$
  Accuracy = \frac{TP + TN}{TP + TN + FP + FN}
  $$  
  - Precision:  
  $$
  Precision = \frac{TP}{TP + FP}
  $$  
  - Recall:  
  $$
  Recall = \frac{TP}{TP + FN}
  $$  
  - F1‑Score:  
  $$
  F1 = 2 \cdot \frac{Precision \cdot Recall}{Precision + Recall}
  $$  

- **Run evaluation via the Run Evaluation button** Executes training, then displays results in the form of tables and graphs.


---

### 📑 Benchmark

This section contains information on the comprehensive evaluation of models:

- **LLM Benchmark Report** Generalized report with key performance and quality metrics for each model.

- **Dataset Overview** - Samples (total number of examples)  
  - Valid Samples (successfully passed validation)  
  - Students / Teachers (distribution by roles in Student–Teacher modes)

- **Validation Success Rate** Percentage of successful validation passes for each model:  
  $$
  Pass\ Rate = \frac{Valid\ Samples}{Total\ Samples} \cdot 100\%
  $$

- **Performance Metrics (Inference Speed)** Measures generation speed:  
  $$
  Velocity = \frac{Time\ (ms)}{Word\ Count}
  $$

- **Quality Metrics Heatmap** Visualization of quality based on:  
  - Coherence  
  - Cognitive Load  
  - Lexical Density  
  - Semantic Overlap  
  - Expansion Ratio

- **Psycholinguistic Signature** Complex model profile:  
  - self_focus  
  - modality  
  - cognitive_density  
  - abstractness  
  - repetition_score  

- **Model Leaderboard** Table with final model scores, ranked by quality and performance.

- **Champion Model** The winner model with the best balance of metrics.  
  - Behavioral Insights: style and cognitive pattern analysis  
  - Strategic Interpretation: explanation of model strengths and weaknesses

---

### 🖥️ Monitor
This section includes:
- Model download interface. 
- List of locally loaded models, their size in GB, and deletion buttons for each model. 
- Reference information in the form of a table with model names that will work adequately with VRAM ~4GB.
- List of installed models (mistral, phi3, tinyllama, llama3, qwen).
- Logging of system events (parameters, time, seed).

---

### ❓ FAQ
- **Why does the Heatmap show 0%?** → Usually caused by a Temperature value that is too high or a weak Teacher model.  
- **What is Blind Mode?** → Generation mode without explicit psychotype designation to check model generalizability.  
- **What is the NLP Science tab for?** → For checking statistical and psycholinguistic features of generated text.  
- **Can this tool be used outside of psychology?** → Yes, for analyzing style, genre, formality, and linguistic diversity.  
- **How to interpret the Scatter Plot (Overlap vs Expansion)?** → Top left corner = creative expansion, bottom right = conservative paraphrasing, center = balanced transformation.  
- **What does Repetition Score mean?** → High values indicate fixation or a limited vocabulary; low values — flexibility.  
- **How is Emotional Stability measured?** → Through the variability of tone between sentences; high variability = dramatic style, low = stable tone.  
- **What is the difference between Frequency Penalty and Presence Penalty?** → Frequency Penalty reduces repetitions, Presence Penalty encourages the appearance of new topics.  
- **Why use a Random Seed?** → For reproducibility of results under identical conditions, which is critical for benchmarking.  
- **What does Champion Model in Benchmark mean?** → The model with the best balance of validation success, speed, and psycholinguistic depth.  
- **How to restore past experiments?** → Use the Experiment Recovery panel in the Sidebar to load JSONL logs and Inject Data.  
- **What is RAG mode needed for?** → Retrieval‑Augmented Generation allows the model to base responses on external context or psychotype data.  
- **Why are some results marked as Noise in Clustering?** → They do not match the expected psychotype cluster and are marked as anomalies.  
- **What does Self‑Critic mode do?** → The model itself evaluates its own output regarding psychotype constraints without a Teacher.  
- **How to check the validity of psychotype emulation?** → In the Model Evaluation tab, select target column = psychotype; validation results will show accuracy.  
- **What is the difference between Single Shot and Sweep Mode?** → Single Shot = one generation; Sweep Mode = a series of runs with parameter variations.  
- **Can results be exported for external analysis?** → Yes, they are logged in JSONL and can be exported to CSV.  
- **What does the Emotional Profile include?** → Subjectivity (TextBlob) and Sentiment (VADER) for measuring emotionality and tone.  
- **Why is Benchmark important?** → It standardizes model evaluation, making comparisons correct and reproducible.  
- **How to interpret Psycholinguistic Signature?** → This is the distribution of traits: self-focus, modality, cognitive density, abstractness, and repeatability.