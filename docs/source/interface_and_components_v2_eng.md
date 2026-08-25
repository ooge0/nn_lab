This document describes the interface of the current version of the application: a FastAPI + Jinja2 + HTMX web app, replacing the original Streamlit interface described in the first "Interface and components" document. It follows the same structure and level of detail as that document, updated to match what is actually implemented, with two sections added that the original did not cover: the per-response evaluation cascade and the database export page. Every field, formula, and page name below is taken directly from the current source code, not carried over from the earlier document without verification. Several formulas differ from the original document because the underlying computation was corrected during this rewrite; each such case is noted explicitly.

The application combines:

* LLM text generation (Ollama, local models only, no paid API) for controlled experiments across different model architectures.
* A structured, multi-layer evaluation cascade that classifies and judges each response before any metric is computed on it.
* Psycholinguistic and statistical analysis (NLTK, TextBlob, spaCy, sentence-transformers) of emotionality, cognitive load, and linguistic pattern metrics.
* Visualization (FastAPI + Plotly + Jinja2/HTMX), providing interactive charts, heatmaps, and clustering views for result interpretation.
* Persistence to JSONL by default, with an on-demand export path into a real SQLite database.


## Interface and components (v2)

### Navigation and interface layout

There is no separate frontend build step. FastAPI serves the API and every HTML page from a single process (`uvicorn api.app:app --reload`). The interface is a fixed left sidebar plus a content area, not a tabbed single page.

* **Sidebar** — grouped into three labeled sections:
  * `[req]` — per-request pages: Generation, Performance, Model Evaluation.
  * `[corpus]` — corpus-level pages, which only produce meaningful output once multiple responses exist: Analytics, NLP Science, Clustering, Benchmark.
  * `[sys]` — system-level pages: System Monitor, Export to DB, FAQ.
* **Service status widget** — a small indicator embedded in the sidebar, checked on every page load, reporting whether Ollama, NLTK resource files, and the spaCy model are reachable. Replaces the original Streamlit sidebar's module status indicators; unlike the original, it does not manage or restart any service, it only reports reachability.
* **Theme toggle** — switches between a dark (VS Code Dark+ derived) and a light palette, persisted client-side.
* No Debug/Lab mode toggle exists. The distinction the original made between "debug" and "laboratory" experiment modes has no equivalent; every page is the same for every use.

### Generation (`/experiments`)

The main experiment-configuration and execution page. Progress is reported live over Server-Sent Events, not by polling or by a Streamlit rerun.

* **Student models** — one or more models to generate with (multi-select, required).
* **Archetypes** — one or more behavioral archetypes to condition generation on (multi-select, required).
* **Biases** — free-text bias descriptor(s) injected into the prompt.
* **Prompt mode** — one of three system-prompt construction strategies:
  * *Behavioral conditioning (Tuned)* — full archetype-aware system prompt.
  * *Blind mode (Hide label)* — generation without an explicit archetype label in the prompt, used to test whether the model still exhibits the target style without being told to.
  * *Raw / No system prompt* — no conditioning at all, a baseline.
* **Judging mode** — one of two, mutually exclusive:
  * *Teacher–student* — a separate teacher model judges every student's output. Requires a teacher model selection.
  * *Self-critic* — the student model judges its own output. A documented sycophancy risk (see "Evaluation cascade" below); the interface does not hide this risk, it is disclosed directly in this document and in the code's own comments.
* **RAG (retrieval-augmented generation)** — optional. When enabled, a retrieval mode (archetype only / archetype + bias) and a Top-K chunk count control what knowledge-base context is injected into the prompt.
* **Sweep** — optional dynamic variation of one generation parameter (Temperature, Top P, Frequency penalty, or Presence penalty) across a range, either by a fixed step (Delta mode) or an explicit minimum/maximum (MIN-MAX mode). Only one parameter can be swept per run; a true multi-parameter grid search is not implemented, by design — the combinatorial cost was judged not worth it for a single machine with no cluster to absorb the extra runtime.
* **Sampling parameters** — Temperature, Top P, Frequency penalty, Presence penalty, Max tokens, Seed. Used as static values unless overridden by an active sweep.
* **Live setup preview** — an HTMX-driven panel that recalculates the exact task count (`students x archetypes x biases x sweep steps`) as the form changes, before the run starts.
* **Hard task-count cap** — a configured ceiling (`max_total_tasks`, default 500) is enforced server-side before generation starts; an oversized request is refused outright with an error, not merely previewed.
* **Stop control** — a cooperative stop: a request to stop is honored between tasks, not mid-generation-call. A response already being generated when stop is requested always finishes and is persisted.

### Evaluation cascade

Not present as a distinct interface section in the original document; this is the core mechanism determining whether a generated response is recorded as valid. It runs automatically on every response, in a fixed, deterministic order — cheapest and most certain checks first, a generative judge only when the earlier layers cannot resolve the case. This ordering is a stated design principle: the cascade is a rule-based pipeline, not an LLM deciding which check to run.

* **Layer 0 — deterministic classification.** Every raw response is classified as one of `VALID`, `MALFORMED_JSON`, `TRUNCATED`, `EMPTY`, or `SCHEMA_ERROR` before any metric is computed on it. A non-`VALID` classification skips metric computation and the judge call entirely, and is recorded as failing.
* **Layer 1 — echo detection.** A response whose semantic-similarity score to its own bias/instruction text is above a calibrated threshold is rejected as an echo — the model repeating its own instruction back instead of generating conditioned text, rather than a genuinely low-similarity, off-topic response. The threshold direction (reject high similarity, not low) was inverted from the initial design after calibration against real generated data showed the opposite intuition was correct for this specific field.
* **Layer 2 — factual-contradiction check.** Only runs when RAG is enabled, since it needs retrieved context to check the response against. Uses a local NLI cross-encoder model. Currently logs a predicted label and a contradiction score on every response but does not reject anything; no rejection threshold has been calibrated against real data yet.
* **Layer 3 — structured judge.** The generative pass/fail judgment: the judge model is asked for structured output and the response is parsed as real JSON, returning a verdict, a confidence value, and a rationale string. A response that fails to parse resolves to a verdict of false with confidence 0.0, a value distinguishable from a genuine negative judgment, not silently indistinguishable from one.

### Performance (`/runs`)

A read-only summary of one completed (or in-progress) run's persisted responses.

* **Run picker** — selects which run's data to summarize.
* **Summary fields** — total records, steps reached, sweep parameter and value range (if any), total processing time, average ms/word, average validation time, teacher(s)/student(s)/prompt strategies/archetypes/biases involved, RAG configuration if enabled.
* **Self-critic vs. teacher-judging comparison** — a two-run picker computing the pass-rate delta between any two runs, most usefully one run judged self-critic and another judged by a teacher model over comparable content. This is explicitly a diagnostic signal, not a correctness check: neither run's pass rate is ground truth, since both a self-critic judge and a teacher judge carry their own biases. A large delta indicates a model inflates its own self-assessment relative to an outside judge; a small delta means the two are broadly consistent for that model. Only a periodic human review of a sample of judged responses can establish which judgment is actually closer to correct — this comparison narrows where to look, it does not replace that review.

### Analytics (`/analytics`)

Three sub-tabs of charts built directly from one run's persisted responses.

* **Adherence & metrics** — adherence heatmap (student x swept value, mean pass rate); workload distribution; latency distribution; generation velocity (ms/word); real generation speed in tokens/second (from Ollama's own reported timing, not a derived estimate); word-count consistency; vocabulary diversity; Levenshtein distance to the prompt/bias text; semantic alignment overlap; a psycholinguistic-signature scatter plot; pass rate and coherence stability by prompt strategy.
* **High-Dim analytics** — two parallel-categories charts (student/teacher/archetype/pass-fail, colored two different ways); a model-productivity matrix (ms/word by student, faceted by teacher); a teacher-impact scatter matrix and a cross-model dependency matrix, both over lexical density, ms/word, and cognitive load.
* **Zipf deviation** — distribution and by-archetype charts over each response's deviation from the word-frequency distribution natural language typically follows (Zipf's law); lower values indicate output closer to typical natural-language statistics.

### NLP Science (`/nlp`)

Three sub-tabs, one linguistic-feature dashboard each, computed via the same metric-computation modules the cascade and analytics pages already use.

* **NLP-1** — part-of-speech morphology profile (adjective/noun/verb distribution); cognitive complexity (readability index vs. lexical diversity); emotional engagement (subjectivity vs. sentiment).
* **NLP-2** — emotional stability (sentiment variance between sentences); repetition/fixation patterns.
* **NLP-3** — sentence-length distribution; self-focus vs. cognitive rigidity, plotted two ways (overall, and split by bias); rigidity distribution by bias type; abstraction vs. cognitive load; narrative coherence distribution; emotional volatility (sentence-to-sentence sentiment variance).

Formula notes, corrected relative to the original document:

* **Cognitive load** is a normalized composite of three quantities — sentence length, punctuation density, and subordinate-clause rate — each min-max normalized to the range [0, 1] before averaging. The original document's formula (complex words divided by total words) described an earlier, unnormalized version where sentence length's raw magnitude dominated the average and the other two components were nearly irrelevant to the result. The current formula:

$$
Cognitive\ Load = \frac{\overline{SentenceLength} + \overline{PunctuationDensity} + SubordinatorRatio}{3}
$$

where each of the first two terms is capped and normalized to [0, 1] before averaging, and the subordinator ratio is naturally bounded to [0, 1].

* **Self-focus index:**

$$
SelfFocus = \frac{Self\ Pronouns}{Total\ Pronouns}
$$

* **Repetition score:**

$$
Repetition = \frac{Repeated\ Tokens}{Total\ Tokens}
$$

* **Sentence rigidity:**

$$
Rigidity = \frac{Imperatives + Repetitions}{Total\ Sentences}
$$

### Clustering (`/clusters`)

Three sub-tabs, over one run's full metric set.

* **K-Means (PCA)** — a PCA-projected scatter plot colored by a chosen dimension, per-axis top feature drivers, and a cluster-purity table.
* **HDBSCAN (Density)** — a density-based clustering scatter over the full-dimensional scaled feature set, with automatic noise/outlier determination.
* **Behavioral topology** — the most complete clustering view: a UMAP dimensionality-reduction projection followed by HDBSCAN clustering, with a minimum-spanning-tree plot and a condensed-tree plot (both may be unavailable on a very small dataset), a feature-correlation matrix and per-feature-pair scatter plots in a research mode, an outlier-by-model breakdown, and the confirmatory cluster-validity indices below.

Cluster-quality indices (unchanged from the original document — these are standard formulas, not affected by the rewrite):

* **Silhouette score:**

$$
s(i) = \frac{b(i) - a(i)}{\max\{a(i), b(i)\}}
$$

where $a(i)$ is the mean distance to points in the same cluster and $b(i)$ is the mean distance to the nearest other cluster.

* **Davies–Bouldin index:**

$$
DBI = \frac{1}{k} \sum_{i=1}^{k} \max_{j \neq i} \frac{\sigma_i + \sigma_j}{d(c_i, c_j)}
$$

* **Adjusted Rand Index (label-alignment against archetype labels):**

$$
ARI = \frac{RI - E[RI]}{\max(RI) - E[RI]}
$$

These three indices are the corpus-level confirmatory-validation layer: they are a separate stage from the per-response cascade above, meaningful only over an accumulated corpus, never over a single response.

### Model Evaluation (`/model_evo`)

* **Target column selection** — any discrete column in the run's metric set with between 2 and 10 unique values (a heuristic filter, not a hard rule about which columns are meaningful targets).
* **Test size** — the train/test split proportion.
* **Fit** — a baseline logistic-regression classifier, trained on the run's numeric metrics to predict the chosen target column.
* **Output** — accuracy, precision, recall, F1-score, a confusion-matrix heatmap, and a feature-importance chart.

$$
Accuracy = \frac{TP + TN}{TP + TN + FP + FN}
\qquad
Precision = \frac{TP}{TP + FP}
\qquad
Recall = \frac{TP}{TP + FN}
\qquad
F1 = 2 \cdot \frac{Precision \cdot Recall}{Precision + Recall}
$$

### Benchmark (`/benchmark`)

A read-only cross-model leaderboard over one run.

* **Overview** — sample counts, valid-sample count, students/teachers involved.
* **Pass rate** — validation success rate per model.
* **Inference speed** — generation speed per model, lower is better.
* **Quality metrics heatmap** — coherence, cognitive load, lexical density, semantic overlap, expansion ratio.
* **Model leaderboard and champion model** — ranked by a composite final score.

$$
FinalScore = 0.4 \cdot PassRate + 0.3 \cdot Coherence + 0.3 \cdot SpeedScore
$$

This formula differs from an earlier version of this leaderboard, which also weighted a "mimicry score" derived from semantic overlap with the bias/archetype text. That component was removed: semantic overlap with the bias text is exactly what the evaluation cascade's Layer 1 uses to detect and reject echo responses, so rewarding a *higher* value of the same measurement the cascade penalizes was a real, direct contradiction between two parts of the same application, not a stylistic choice. No comparable replacement metric ("closeness to a teacher's reference output") exists in the persisted data today, so the weight was redistributed rather than replaced with an unvalidated substitute.

### System Monitor (`/monitor`)

Deliberately narrow, by an explicit scope decision: a read-only schema and data inspector, not a service-management panel.

* **Schema/dtype table** — every column present in the run's data, with its inferred data type and non-null count.
* **Raw data preview** — the run's responses as a plain table.

Ollama model management (pulling, listing, deleting models) is not part of this page. The original document described a model-download interface and per-model deletion buttons; that functionality exists only as a separate, deliberately out-of-scope concern here, since it involves subprocess execution and destructive deletion, a different risk profile from the rest of this read-only page. Model management is done from a terminal directly (`ollama pull`, `ollama list`, `ollama rm`), or via the operational console described below.

### Export to Database (`/db_export`)

Not present in the original document; this page did not exist until the underlying storage adapter was wired to a live endpoint.

Every response is stored as JSONL files by default. A second, fully-tested storage backend exists over real SQLite tables (`runs`, `responses`), useful for ad-hoc SQL queries against accumulated results; it is not the default write path, only an on-demand copy.

* **Run list** — every known run, with its ID, start time, and total task count.
* **Send to DB** — copies one run's metadata and every response into the SQLite database. Re-sending an already-exported run is refused by default, with a clear message, rather than silently duplicating every response row; a separate re-export action performs an explicit overwrite.
* **Bulk selection** — checkboxes plus a "send selected" action. Bulk export triggers each selected row's own individual export action; every row still resolves independently, with the same already-exported/overwrite behavior a single click would produce.
* **Export status column** — reports either "not synced" or the exact date and time a run was last copied into the database, refreshed live after an export completes, without a page reload.

The same operation is available from a terminal with no server running, via the operational console (`python -m cli.manage export-db <run_id>`), and as a raw API call (`POST /db_export/export?run_id=...`).

### Operational console

Not present in the original document, which had no equivalent to a headless administrative interface. A command-line entry point for operations that do not require the web interface to be running:

* `serve` — starts the web application (equivalent to the documented `uvicorn` command).
* `status` — reports Ollama, NLTK, and spaCy reachability, the same checks the sidebar's service-status widget performs, in a terminal-readable form.
* `list-runs` — lists every known run.
* `export-db <run_id>` — the command-line equivalent of the Export to Database page.

### FAQ (`/faq`)

A static user-guide and methodology reference page, available in English and Ukrainian.

* Why does the adherence heatmap show 0%? — Usually a Temperature value set too high, or a weak teacher model.
* What is Blind mode for? — Testing whether a model still produces the target archetype's style without being told the archetype name.
* What does the evaluation cascade check, and in what order? — See "Evaluation cascade" above; Layer 0 first, Layer 3 (the generative judge) last.
* What is the difference between Self-critic and Teacher–student judging? — Self-critic uses the same model to generate and judge, a documented risk of the model favoring its own output; Teacher–student uses a separate model to judge.
* How is the self-critic-vs-teacher-judging delta meant to be used? — As a diagnostic of how much a model over-trusts its own judgment relative to an outside model, not as a determination of which judgment is correct.
* Why was the leaderboard's mimicry score removed? — It rewarded exactly the behavior the evaluation cascade's Layer 1 is built to reject; see "Benchmark" above.
* What is RAG mode for? — Retrieval-augmented generation: injecting knowledge-base context relevant to the archetype and/or bias into the generation prompt.
* Can results be used outside psycholinguistic style analysis? — Yes; the same metrics apply to any style, genre, formality, or linguistic-diversity comparison task, not only the archetype-conditioning use case this application was built around.
* Where does data actually live? — JSONL files by default; SQLite only if explicitly exported via the Export to Database page or console command.
