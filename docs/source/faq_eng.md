This program is a specialized benchmarking suite designed for the quantitative assessment of how large language models (LLMs) adapt to different constraints, behavioral profiles, and knowledge contexts under various hyperparameters. It allows users to systematically vary generation settings, prompting strategies, evaluation modes, and retrieval conditions while observing how these changes affect the cognitive, semantic, linguistic, and stylistic characteristics of generated text. The platform combines synthetic data generation, behavioral testing, model evaluation, clustering, and advanced metrics collection within a unified workflow. Thus, the tool provides not only performance measurement but also deeper insight into model behavior, response stability, behavioral drift, and psycholinguistic patterns across different experimental conditions.


It combines:

* LLM text generation (Ollama / local models), providing controlled experiments with different architectures.
* Psycholinguistic analysis (NLTK / TextBlob), which allows for evaluating emotionality, cognitive load, and linguistic patterns.
* Statistical assessment of model behavior, including metrics of consistency, repeatability, and semantic overlap.
* Visualization (Streamlit + Plotly), which provides interactive charts, heatmaps, and clustering for result interpretation.

This suite creates a unified research environment where experiments, analysis, and real-time monitoring can be combined, making it useful for both academic research and applied model optimization tasks.

## 🛠️ Interface and components

### Sidebar (lab controls + debug/recovery)

The sidebar is the main control block for the experiment:

* **Toggle debug/lab** switch between debug and laboratory experiment modes.

* **Debug preset** - *Modules*: active modules (**Ollama**, **NLP**) with status indicators.

  * *Modes*: **SC (self-critic)**, **T-S (teacher–student)**.

* **Lab controls (baseline parameters)** panel for configuring static hyperparameters:

  * **Temperature** — controls the level of randomness in the response. Low values → more predictable and logical texts; high values → creative but less stable.
  * **Top P** — determines which tokens are considered when choosing the next word (filtering by probability). A smaller value → more controlled output.
  * **Frequency penalty** — reduces the likelihood of reusing the same words or phrases.
  * **Presence penalty** — encourages the appearance of new topics or words to avoid monotony.
  * **Max tokens** — limits the maximum response length (number of generated tokens).
  * **Random seed** — sets the initial value for the randomness generator, allowing for the reproduction of the same results with identical settings.

  Buttons:

  * **Save JSONL** — saving experiment results to a file
  * **Clear history** — clearing the run history

* **Experiment recovery** - loading previous experiments (e.g., `lab_ex...85042.jsonl`)

  * **Inject data** — reusing data in a new run or loading previously generated data

---

### 🚀 Syntethic data

This section describes the generation and model interaction mechanisms:

* **Model interaction modes:** - *Student–teacher* — the student model learns from examples of the teacher model.

  * *Self-critic* — the model evaluates its own output without an external teacher.
  * *Single shot* — one-time generation without additional iterations.

* **Experiment hyperparameter setup modes:** - *None* — static parameters are taken from the *Baseline parameters* tab.

  * *Sweep mode* — dynamic hyperparameter range, which can be set via:

    * **Delta** — changing the parameter by a fixed step.
    * **Min-max** — generation within a specified range.

* **Sweep-experiments** performed for parameters: Temperature, Top P, Frequency penalty, Presence penalty.
  Formally:
  $$
  Sweep(Parameter) = {p_{min}, p_{min} + \Delta, \dots, p_{max}}
  $$

* **Prompt strategies:** - *Expert psychologist* — strategy with an emphasis on psycholinguistic features.

  * *Blind mode* — without explicit psychotype designation.
  * *Raw baseline* — basic prompt without additional modifications.

* **RAG (retrieval augmented generation):** support for modes: *Psychotype only* and *Full context*.
  The Top-K parameter determines the number of relevant documents to load:
  $$
  Context = {d_1, d_2, \dots, d_K}
  $$

* **Bias split function:** allows for separating the influence of systemic and user biases in generation.

* **Text generation for different psychotypes:** Baseline, Hysteroid, Paranoid, Schizoid.

* **Experiment progress display:** - during generation, the experiment execution status is displayed.

  * upon completion, results are saved in JSONL format with timestamps and statuses (**OK / Fail**) manually if needed.

---

### 📊 Runtime metrics

This section describes model performance and latency metrics:

* **Speed and latency metrics** measure the efficiency of text generation and validation.

* **Velocity (generation speed):** formula for calculating the average time per word:
  $$
  Velocity = \frac{Time\ (ms)}{Word\ Count}
  $$

* **Total generation + validation time** includes the total time spent creating the text and its verification.

* **Summary for each experiment:** - records (number of records)

  * steps (number of steps)
  * sweep parameter (the variable parameter)
  * value range (range of values)
  * avg. ms/word (average time per word)
  * avg. validation time (average validation time)

* **Raw experiment logs** display of the experiment result in tabular form.

---

### 📈 Behavioral analytics

This section describes tools for analyzing the style and quality of generations:

* **Scatter plot: semantic overlap vs expansion** used to visualize the relationship between semantic overlap and text expansion.
  Formally:
  $$
  Overlap = \frac{|Tokens_{gen} \cap Tokens_{ref}|}{|Tokens_{ref}|}
  $$
  $$
  Expansion = \frac{|Tokens_{gen}|}{|Tokens_{ref}|}
  $$

* **Scatter plot interpretation:** - top left corner → creative expansion (low overlap, high expansion)

  * bottom right corner → conservative paraphrasing (high overlap, low expansion)
  * center → balanced transformation

* **Visualization of hyperparameter influence on style and quality** study of the dependency between Temperature, Top P, Penalties, and text characteristics.
  For example:
  $$
  Style\ Shift = f(Temperature, TopP, Penalties)
  $$

* **Verification success heatmap** shows the percentage of successful generations for different parameter combinations:
  $$
  Success\ Rate = \frac{Valid\ Generations}{Total\ Generations} \cdot 100%
  $$

---

### 🧪 NLP features

#### POS morphology profile

Part-of-speech distribution:

* ADJ (adjectives)
* NOUN (nouns)
* VERB (verbs)

**Interpretation:**

* more ADJ → emotional, descriptive style
* more NOUN → object-oriented style
* more VERB → dynamic, active style

#### Cognitive complexity: ARI + TTR (readability vs diversity)

$$
Cognitive\ Load = \frac{Complex\ words}{Total\ number\ of\ words}
$$

* ARI (readability index)
* corrected TTR (lexical diversity)

**Purpose:** measuring the level of abstraction and cognitive load.

#### Emotional profile: (subjectivity vs sentiment)

$$
Subjectivity = \frac{Subjective\ words}{Total\ number\ of\ words}
$$

$$
Sentiment = \frac{Positive - Negative}{Total}
$$

* Subjectivity (TextBlob)
* Sentiment (VADER)

**Purpose:** determining the emotionality and objectivity of the text.

#### Emotional stability (sentiment variance)

Measures the fluctuation of emotional tone between sentences.

* high variability → dramatic / unstable style
* low → stable / neutral style

#### Repetition score

$$
Repetition = \frac{Repeated\ tokens}{Total\ number\ of\ tokens}
$$

Evaluates the frequency of repeating words and structures.

* high value → fixation / limited thinking
* low value → flexible vocabulary

#### Sentence structure

$$
Rigidity = \frac{Imperatives + Repetitions}{Total\ Sentences}
$$

Average sentence length for each psychotype.

* short sentences → control / rigidity
* long sentences → narrativity / expressiveness

#### Self-focus index

$$
SelfFocus = \frac{Self\ Pronouns}{Total\ Pronouns}
$$

#### Processing speed

$$
\text{Velocity} = \frac{\text{Time (ms)}}{\text{Word Count}}
$$

#### Latency

Total generation and response validation time.

---

#### 📈 Scatter plot interpretation (overlap vs expansion)

* **Top left corner:** creative expansion
* **Bottom right corner:** conservative paraphrasing
* **Center:** balanced content transformation

---

### 🧩 Embedding clusters

* **Advanced density clustering (UMAP + HDBSCAN)** used for latent space analysis and identifying structures in data.

  * **UMAP** — uniform manifold approximation and projection. Dimensionality reduction preserving local and global structure.
  * **HDBSCAN** — density-based clustering with automatic noise determination.
    References:

    * HDBSCAN:

      * [How HDBSCAN Works](https://hdbscan.readthedocs.io/en/latest/how_hdbscan_works.html)
      * UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction (2018)

        * PDF: https://arxiv.org/pdf/1802.03426
      * Shapley-based explainable AI for clustering applications in fault diagnosis and prognosis

        * DOI:10.1007/s10845-024-02468-2
      * Unsupervised Learning: Comparative Analysis of Clustering Techniques on High-Dimensional Data

        * PDF: https://arxiv.org/html/2503.23215v1
      * The Information Geometry of UMAP

        * PDF: https://hal.science/hal-04819511v1/file/umap_information_geometry.pdf
      * Dim Reduction & Vis. Advanced Data Visualization. CS 6965. Fall 2019. Prof. Bei Wang Phillips University of Utah

        * https://www.sci.utah.edu/~beiwang/teaching/cs6965-fall-2019/Lecture02-DR.pdf
      * Clustering, Regression and Vis. Advanced Data Visualization. CS 6965. Fall 2019. Prof. Bei Wang Phillips University of Utah

        * https://www.sci.utah.edu/~beiwang/teaching/cs6965-fall-2019/Lecture06-Clustering.pdf

* **Parameters:** - *Min cluster size* — minimum number of points in a cluster.

  * *Min samples* — minimum number of neighbors to determine density.
  * *Neighbors* — number of neighbors for building the graph in UMAP.
  * *Min distance* — minimum distance between points in the projection.

* **Latent space analysis + minimum spanning tree (MST)** used to visualize paths between clusters and analyze their topology.

* **Clustering quality indices:**

  * **CPI (silhouette):**

$$
s(i) = \frac{b(i) - a(i)}{\max{a(i), b(i)}}
$$

where $$a(i)$$ is the average distance to points in its cluster, $$b(i)$$ is the minimum average distance to another cluster.

* **RMSEA (DBI – Davies–Bouldin index):**

$$
DBI = \frac{1}{k} \sum_{i=1}^{k} \max_{j \neq i} \frac{\sigma_i + \sigma_j}{d(c_i, c_j)}
$$

where $$\sigma_i$$ is the average deviation in cluster $$i$$, $$d(c_i, c_j)$$ is the distance between centroids.

* **ARI (adjusted Rand index):**
  $$
  ARI = \frac{RI - E[RI]}{\max(RI) - E[RI]}
  $$

where $$RI$$ is the Rand index, measuring the consistency of clustering with baseline labels.

* **Behavioral anomaly analysis** identification of outliers (anomalous generations) that do not match expected psychotypes.

  * Outlier percentage:

$$
Outlier\ Rate = \frac{N_{outliers}}{N_{total}} \cdot 100%
$$

* Examples of texts from clusters and noise points.

* **Noise detection** generations that do not match the psychotype are automatically marked as *Noise* and excluded from the main analysis.

---

### 🧬 LLM evaluation

This section contains information on the comprehensive evaluation of models:

* **Metric evaluation (linguistic / neuro)** for predicting target labels:

  * hallucination
  * truthful output
  * anomaly
  * psychotype

* **Dropdown for selecting target column** allows choosing the target column for prediction.

* **Test size (train/test split)** determines the proportion of data for training and testing:
  
  $$
  Train\ Size + Test\ Size = 1
  $$

* **Evaluation metrics:** - accuracy:

  $$
  Accuracy = \frac{TP + TN}{TP + TN + FP + FN}
  $$

  * precision:
  
    $$
    Precision = \frac{TP}{TP + FP}
    $$
  * recall:
  
    $$
    Recall = \frac{TP}{TP + FN}
    $$
  * F1-score:
  
    $$
    F1 = 2 \cdot \frac{Precision \cdot Recall}{Precision + Recall}
    $$

* **Run evaluation via the Run Evaluation button** executes training, then displays results in the form of tables and graphs.

---

### 📑 Benchmark

This section contains information on the comprehensive evaluation of models:

* **LLM benchmark report** generalized report with key performance and quality metrics for each model.

* **Dataset overview** - samples (total number of examples)

  * valid samples (successfully passed validation)
  * students / teachers (distribution by roles in Student–Teacher modes)

* **Validation success rate** percentage of successful validation passes for each model:
  $$
  Pass\ Rate = \frac{Valid\ Samples}{Total\ Samples} \cdot 100%
  $$

* **Performance metrics (inference speed)** measures generation speed:
  $$
  Velocity = \frac{Time\ (ms)}{Word\ Count}
  $$

* **Quality metrics heatmap** visualization of quality based on:

  * coherence
  * cognitive load
  * lexical density
  * semantic overlap
  * expansion ratio

* **Psycholinguistic signature** complex model profile:

  * self_focus
  * modality
  * cognitive_density
  * abstractness
  * repetition_score

* **Model leaderboard** table with final model scores, ranked by quality and performance.

* **Champion model** the winner model with the best balance of metrics.

  * Behavioral insights: style and cognitive pattern analysis
  * Strategic interpretation: explanation of model strengths and weaknesses

---

### 🖥️ System monitor

This section includes:

* Model download interface.
* List of locally loaded models, their size in GB, and deletion buttons for each model.
* Reference information in the form of a table with model names that will work adequately with VRAM ~4GB.
* List of installed models (mistral, phi3, tinyllama, llama3, qwen).
* Logging of system events (parameters, time, seed).

---

### ❓ FAQ``

* **Why does the heatmap show 0%?** → Usually caused by a Temperature value that is too high or a weak Teacher model.
* **What is blind mode?** → Generation mode without explicit psychotype designation to check model generalizability.
* **What is the NLP features tab for?** → For checking statistical and psycholinguistic features of generated text.
* **Can this tool be used outside of psychology?** → Yes, for analyzing style, genre, formality, and linguistic diversity.
* **How to interpret the scatter plot (overlap vs expansion)?** → Top left corner = creative expansion, bottom right = conservative paraphrasing, center = balanced transformation.
* **What does repetition score mean?** → High values indicate fixation or a limited vocabulary; low values — flexibility.
* **How is emotional stability measured?** → Through the variability of tone between sentences; high variability = dramatic style, low = stable tone.
* **What is the difference between Frequency penalty and Presence penalty?** → Frequency penalty reduces repetitions, Presence penalty encourages the appearance of new topics.
* **Why use a Random seed?** → For reproducibility of results under identical conditions, which is critical for benchmarking.
* **What does Champion model in Benchmark mean?** → The model with the best balance of validation success, speed, and psycholinguistic depth.
* **How to restore past experiments?** → Use the Experiment Recovery panel in the Sidebar to load JSONL logs and Inject Data.
* **What is RAG mode needed for?** → Retrieval-augmented generation allows the model to base responses on external context or psychotype data.
* **Why are some results marked as Noise in Clustering?** → They do not match the expected psychotype cluster and are marked as anomalies.
* **What does Self-critic mode do?** → The model itself evaluates its own output regarding psychotype constraints without a Teacher.
* **How to check the validity of psychotype emulation?** → In the LLM Evaluation tab, select target column = psychotype; validation results will show accuracy.
* **What is the difference between Single shot and Sweep mode?** → Single shot = one generation; Sweep mode = a series of runs with parameter variations.
* **Can results be exported for external analysis?** → Yes, they are logged in JSONL and can be exported to CSV.
* **What does the emotional profile include?** → Subjectivity (TextBlob) and Sentiment (VADER) for measuring emotionality and tone.
* **Why is Benchmark important?** → It standardizes model evaluation, making comparisons correct and reproducible.
* **How to interpret Psycholinguistic signature?** → This is the distribution of traits: self-focus, modality, cognitive density, abstractness, and repeatability.
