Glossary
==========

A comprehensive reference for the AI/LLM, machine-learning, NLP, and (psycho)linguistic vocabulary
used across this project's code and docs -- both textbook terms and this project's own specific
usage of them. Definitions are written to be correct in general **and** accurate to how the term is
actually used in this codebase; where the two could be confused, that's called out explicitly.

Every term is a genuine cross-reference target -- use ``:term:`Term Name``` anywhere in the docs to
link back here.

.. important::
   **Two completely different metrics in this project share the abbreviation "ARI."**
   :term:`Automated Readability Index (ARI)` (a per-response *readability* score,
   ``readability_ari`` in persisted data) and :term:`Adjusted Rand Index (ARI)` (a corpus-level
   *cluster-validity* score) measure nothing alike and are computed by entirely different modules
   (:mod:`core.analysis.nlp_science` vs. :mod:`core.services.cluster_discovery`). Both are named
   distinctly below specifically so this collision can't be missed -- exactly the kind of
   naming-vs-meaning gap this project's own "measurement validity" discipline exists to catch (see
   :doc:`wiki/04-llm-analytics`'s ``semantic_overlap`` and benchmark-leaderboard stories for two real
   examples of the same class of mistake).

LLM / generative AI fundamentals
------------------------------------

.. glossary::
   :sorted:

   Large Language Model (LLM)
      A neural network, typically transformer-based, trained on large text corpora to predict and
      generate text. This project treats LLMs (served locally via Ollama) as the subject under
      test, not as a tool it trusts by default -- the entire judge/cascade pipeline exists because
      an LLM's own claims about its output can't be taken at face value.

   Prompt
      The input text given to an LLM to elicit a response. See :term:`System prompt` for the
      specific role-tagged variant this project always uses.

   System prompt
      The role-tagged instruction text sent to a chat-style LLM API separately from the user's own
      message, typically carrying persistent behavioral instructions. This project's
      :class:`~core.domain.interfaces.PromptStrategy` builds the system prompt per generation call,
      encoding the target :term:`archetype` and :term:`bias`.

   Completion
      The text an LLM generates in response to a prompt. Reaches this project as
      :class:`~core.domain.entities.GenerationResult`.

   Token
      The unit an LLM actually processes text as -- typically a sub-word fragment, not a whole
      word (via a tokenizer like BPE). Distinct from this project's own *linguistic* word-count
      metrics (:term:`Type-Token Ratio (TTR)`, etc.), which tokenize on whitespace/NLTK rules, not
      an LLM's own subword vocabulary -- ``prompt_tokens``/``completion_tokens`` (Ollama's own
      counts) and ``word_count`` (NLTK-tokenized) are genuinely different units in the same
      persisted record.

   Tokenization
      Splitting text into discrete units for processing. Ambiguous on its own -- this project uses
      it in two unrelated senses: an LLM's subword tokenization (see :term:`Token`) and NLTK's
      word-level tokenization (``word_tokenize``) that every linguistic metric in
      :mod:`core.analysis.nlp_science` is built on.

   Context window
      The maximum number of tokens an LLM can attend to in a single call (prompt + completion
      combined). Not directly configured anywhere in this project's code today -- ``max_tokens`` on
      :class:`~core.domain.interfaces.LLMClient` caps generation length, not context window size.

   Temperature
      A sampling parameter controlling randomness in next-token selection -- near 0 is close to
      :term:`Greedy decoding` (deterministic, most-likely token every time), higher values flatten
      the probability distribution, favoring less-likely tokens more often. The project's primary
      swept parameter (:attr:`~core.domain.entities.ExperimentConfig`'s sweep fields), used
      throughout :doc:`wiki/04-llm-analytics` to study how output behavior shifts across its range.

   Top-p (nucleus sampling)
      A sampling parameter: restricts next-token choice to the smallest set of tokens whose
      cumulative probability reaches ``p`` (e.g. ``top_p=0.9`` samples only from the tokens making
      up the top 90% of probability mass), discarding the unlikely long tail regardless of how many
      tokens that is. A second parameter this project's sweep can vary.

   Frequency penalty
      A sampling parameter that lowers the likelihood of tokens proportionally to how often they've
      already appeared in the generated text so far -- discourages verbatim repetition.

   Presence penalty
      A sampling parameter that lowers the likelihood of any token that has appeared at all so far,
      regardless of how many times -- a flat penalty (unlike :term:`Frequency penalty`'s
      count-proportional one), pushing toward topic diversity rather than just avoiding repeats.

   Sampling
      The general process of choosing the next token from an LLM's predicted probability
      distribution -- :term:`Temperature`, :term:`Top-p (nucleus sampling)`, :term:`Frequency
      penalty`, and :term:`Presence penalty` all shape this process.

   Greedy decoding
      Always picking the single most probable next token -- the deterministic limit of
      :term:`Sampling` as :term:`Temperature` approaches 0. Produces the same output for the same
      input every time; standard sampling does not.

   Inference
      Running a trained model forward to produce an output (as opposed to training it). Every
      Ollama call this project makes is an inference call.

   Hallucination
      An LLM generating content that is fabricated, unsupported, or contradicts the context it was
      given, stated with the same fluency and confidence as accurate content. This project's own
      hallucination check (:func:`core.analysis.hallucination_check.check_hallucination`) narrows
      this to one specific, checkable sense: does the response contradict :term:`Retrieval-Augmented
      Generation (RAG)`-retrieved context, per a local :term:`Natural Language Inference (NLI)`
      model -- see :doc:`wiki/04-llm-analytics` for exactly what this does and does not cover, and
      why it doesn't gate anything yet.

   Zero-shot
      Asking a model to perform a task with no worked examples in the prompt, relying entirely on
      its pretrained knowledge and instructions. This project's :class:`~core.domain.interfaces
      .PromptStrategy` builds zero-shot prompts -- no example rewrites are included anywhere in the
      pipeline.

   Few-shot
      Asking a model to perform a task with a small number of worked examples included in the
      prompt, to steer its behavior via demonstration rather than instruction alone. Not used
      anywhere in this project (see :term:`Zero-shot`).

   Quantization
      Reducing a model's numeric precision (e.g. 16-bit floats down to 4-bit integers) to shrink
      memory footprint and speed up inference, at some cost to output quality. Ollama serves
      quantized models by default (:term:`GGUF` format) -- directly relevant to this project's
      repeated "weak machine, no heavy compute" constraint.

   GGUF
      A quantized model file format used by ``llama.cpp`` and, by extension, Ollama. Mentioned in
      :doc:`wiki/03-feature-implementation`'s interpretability-debt section specifically because
      TransformerLens does not support it -- one concrete reason gradient-level interpretability
      tooling can't be pointed at this project's actual model-serving path without a second,
      parallel model-loading route.

   Self-critic
      A judging mode where the same model that generated a response also judges it (as opposed to
      :term:`Teacher-student`). Carries a real risk (sycophancy -- see
      :doc:`wiki/04-llm-analytics`): a model may be systematically lenient toward its own output.

   Teacher-student
      A judging mode where a distinct "teacher" model judges a "student" model's response, as
      opposed to :term:`Self-critic`. Named after the model-distillation sense of these words, but
      this project doesn't perform distillation -- it's evaluation-only routing.

Retrieval-Augmented Generation (RAG)
------------------------------------------

.. glossary::
   :sorted:

   Retrieval-Augmented Generation (RAG)
      Retrieving relevant text from an external knowledge source and inserting it into an LLM's
      prompt before generation, so the model can ground its output in that content rather than
      relying purely on what it memorized during training. Implemented in
      :mod:`core.adapters.rag`, optional per run (``rag_enabled``).

   Embedding
      A dense numeric vector representing text's meaning, positioned in a high-dimensional space
      such that semantically similar texts land near each other. This project uses
      ``all-MiniLM-L6-v2`` (:class:`sentence_transformers.SentenceTransformer`) for both RAG
      retrieval and the ``semantic_overlap`` metric -- the same model, reused rather than adding a
      second one to the dependency footprint.

   Vector store
      A data structure/index for storing embeddings and finding the nearest ones to a query vector
      quickly. This project's :mod:`core.adapters.rag.vector_store` wraps FAISS
      (``faiss-cpu``) for this.

   Chunk / Chunking
      Splitting a knowledge-base document into smaller pieces ("chunks") small enough to embed and
      retrieve individually. :mod:`core.adapters.rag.chunking` does this for this project's
      knowledge-base text files.

   Top-k retrieval
      Retrieving the ``k`` most similar chunks to a query (by :term:`Cosine similarity` between
      embeddings), rather than a similarity-threshold cutoff. This project's ``rag_top_k``
      configuration value.

   Knowledge base
      The corpus of reference text a RAG system retrieves from. Here: the archetype-behavior text
      files under ``knowledge/rag/`` (see CLAUDE.md SS5 for a note on their current file naming).

LLM evaluation and the judge/cascade pipeline
-----------------------------------------------------

.. glossary::
   :sorted:

   LLM-as-judge
      Using an LLM to evaluate another (or its own) output, rather than a human or a fixed rule --
      this project's :class:`~core.adapters.structured_judge.StructuredJudge` is Layer 3 of the
      cascade (see :term:`Cascade (evaluation cascade)`).

   Verdict
      The pass/fail decision a judge produces for one response. Persisted as ``v_ok``/
      ``v_ok_numeric``; :class:`~core.domain.entities.JudgeVerdict` is the structured entity
      carrying it alongside :term:`Confidence (judge)` and :term:`Rationale`.

   Confidence (judge)
      A judge's own stated certainty in its verdict, ``0.0``-``1.0``. Left ``None`` (not faked)
      when the judge model doesn't supply one -- see :doc:`wiki/04-llm-analytics` for why that
      distinction matters (a real, if fixable, gap the pre-2026-08-24 ``NaiveJudge`` had).

   Rationale
      A judge's one-sentence natural-language explanation for its verdict. As of the 2026-08-24
      :class:`~core.adapters.structured_judge.StructuredJudge` fix, a parse failure produces a
      *distinguishable* rationale ("...not valid JSON...") rather than silently looking identical
      to a genuine "no" -- CLAUDE.md SS4's original top-priority defect.

   Structured output / JSON mode
      Requesting (and, critically, actually parsing) a model's response as machine-readable JSON
      matching a declared shape, rather than free-form text a caller has to guess at. The literal
      fix at the center of the 2026-08-24 judge rewrite: the prior ``NaiveJudge`` requested JSON
      mode but decided pass/fail via ``"true" in text.lower()``, discarding the structure entirely.

   Cascade (evaluation cascade)
      This project's four-layer per-response evaluation pipeline (CLAUDE.md SS3a): Layer 0
      (deterministic validity gates), Layer 1 (embedding-based echo detection), Layer 2 (NLI
      factual-contradiction check against RAG context), Layer 3 (the LLM judge). Routing between
      layers is static Python control flow, deliberately **not** LLM-orchestrated -- see
      :doc:`wiki/04-llm-analytics` for exactly what's built, what's gating, and what's still the
      author's own future work.

   Regression fence
      A test that deliberately pins *today's known-wrong* behavior, so it can't silently drift
      further without a test noticing -- distinct from a normal test asserting correct behavior.
      Named and used this way in :doc:`wiki/06-qa-testing-strategy`; the original
      ``test_naive_judge.py``'s malformed-input test was the clearest example until the judge fix
      made it a correctness test instead.

   Construct validity
      Whether a measurement actually captures the underlying concept it claims to measure (as
      opposed to *reliability*, whether it measures *something* consistently). This project's
      stated core differentiator (CLAUDE.md SS0) is demonstrating construct validity work directly
      -- e.g. :func:`~core.services.cluster_discovery.compute_fit_indices`'s docstring frames
      Silhouette/Davies-Bouldin/ARI explicitly as "construct-validity proxies, not a pass/fail
      judgment."

   Ground truth
      A trusted, independently-known-correct label to compare a system's output against. This
      project has only two real sources of it today: the :term:`archetype` label chosen at
      generation time, and (self-referentially) the judge's own verdict -- no human-annotation
      surface exists yet, a named, disclosed gap in :doc:`wiki/04-llm-analytics`.

   Cross-encoder
      A model architecture that takes *two* texts as joint input and scores their relationship
      directly (as opposed to a *bi-encoder*, which embeds each text separately and compares
      vectors afterward -- see :term:`Embedding`). Slower per-pair but typically more accurate for
      pairwise tasks. This project's Layer 2 hallucination check uses
      ``cross-encoder/nli-MiniLM2-L6-H768`` for exactly this reason.

Natural Language Inference and classification
-----------------------------------------------------

.. glossary::
   :sorted:

   Natural Language Inference (NLI)
      The task of deciding whether one text (the "hypothesis") is logically supported by, contradicts,
      or is unrelated to another (the "premise") -- see :term:`Entailment`, :term:`Contradiction (NLI
      label)`, :term:`Neutral (NLI label)`. This project's Layer 2 (:mod:`core.analysis
      .hallucination_check`) applies NLI with the RAG-retrieved context as premise and the
      response as hypothesis.

   Entailment
      An NLI label: the hypothesis logically follows from the premise -- it's a reasonable
      restatement or logical consequence, not new or conflicting information.

   Contradiction (NLI label)
      An NLI label: the hypothesis conflicts with the premise -- they can't both be true. The label
      this project's Layer 2 check treats as a signal worth logging (not yet gating -- see
      :term:`Cascade (evaluation cascade)`).

   Neutral (NLI label)
      An NLI label: the hypothesis is neither supported nor contradicted by the premise -- plausible
      but unconfirmed by it, or simply unrelated.

   Softmax
      A function converting a vector of raw scores ("logits") into a probability distribution that
      sums to 1. :func:`core.analysis.hallucination_check.check_hallucination` applies this to the
      NLI cross-encoder's raw output before reporting ``contradiction_score``.

Core NLP techniques
------------------------

.. glossary::
   :sorted:

   Part-of-speech tagging (POS tagging)
      Labeling each word in text with its grammatical category (noun, verb, adjective, ...).
      :class:`~core.analysis.nlp_science.PsychScientist` uses NLTK's tagger, grouped into
      NOUN/VERB/ADJ/ADV for the ``pos_distribution`` metric.

   Dependency parsing
      Analyzing a sentence's grammatical structure as a tree of directed links ("dependencies")
      between words, rather than a flat sequence of POS tags -- captures *which* words modify or
      depend on *which* others, and how far apart they are. Performed by spaCy in
      :mod:`core.analysis.syntactic_complexity`; see :term:`Dependency distance`.

   Dependency distance
      The distance (in words, or tree-edges) between two syntactically related tokens in a
      dependency parse. A validated syntactic-complexity marker independent of raw sentence length
      -- this project's ``dependency_distance`` metric, via spaCy + TextDescriptives.

   Lemmatization
      Reducing a word to its dictionary base form (e.g. "running" -> "run"), as opposed to
      *stemming*, which crudely chops suffixes without guaranteeing a real word results. Used by
      NLTK's WordNet-based lookups in :meth:`~core.analysis.nlp_science.PsychScientist.analyze_text`
      (the ``abstract_ratio`` heuristic).

   Stopword
      A very common word (e.g. "the," "is," "and") typically filtered out before analyzing content
      words, since it carries little topical meaning on its own. NLTK's English stopword list
      backs this project's ``lexical_density`` metric.

   N-gram
      A contiguous sequence of ``n`` tokens from text (a *unigram* is one token, a *bigram* is two,
      etc.). Not directly computed as its own metric in this project, but the underlying unit
      behind :term:`TF-IDF` and several corpus-frequency techniques.

   Corpus
      A structured collection of text used for analysis or training. Used in two senses in this
      project: the reference/background corpus a technique like :term:`TF-IDF` might be normalized
      against, and this project's own accumulated response records (the "corpus-level confirmatory
      analysis" of CLAUDE.md SS3b) -- the second sense is this project's dominant one.

   Lexicon
      A structured word list, often tagged with categories or scores, used for rule-based text
      analysis. This project's own hand-built lexicons (``self_pronouns``, ``modal_verbs``,
      ``hedge_words``, ``booster_words``, and others in
      :class:`~core.analysis.nlp_science.PsychScientist`) are all lexicon-ratio metrics -- simple,
      interpretable, and explicitly *not* validated against an external gold-standard lexicon like
      LIWC.

   TF-IDF
      "Term Frequency - Inverse Document Frequency": a classic weighting scheme scoring a word
      highly in a document if it appears often *there* but rarely across the wider collection --
      surfaces distinctive words rather than merely frequent ones. This project's ``coherence``
      metric vectorizes sentences with TF-IDF, then measures :term:`Cosine similarity` between
      consecutive sentences -- explicitly *not* a learned embedding (see :term:`Embedding`), a
      distinction :doc:`wiki/04-llm-analytics` calls out directly.

   Cosine similarity
      A similarity measure between two vectors based on the angle between them (1.0 = identical
      direction, 0 = orthogonal/unrelated, can go negative), independent of vector magnitude. Used
      throughout this project for both TF-IDF vectors (``coherence``) and real embeddings
      (``semantic_overlap``, RAG retrieval) -- the same math, applied to two different kinds of
      vector.

   Sentence embedding
      An :term:`Embedding` representing an entire sentence (or short passage) as one vector, as
      opposed to a per-word embedding. ``all-MiniLM-L6-v2`` produces these for this project.

   Semantic similarity
      How close two texts are in *meaning*, as opposed to *surface* overlap (see :term:`TF-IDF`,
      which measures surface token overlap-weighted-by-rarity, not meaning). This project's
      ``semantic_overlap`` field is a real semantic-similarity score (fixed 2026-08-24 from a
      former plain Jaccard token-overlap computation that shared the name but not the technique --
      see :doc:`wiki/04-llm-analytics`'s "A fixed naming/technique gap").

   Sentiment analysis
      Automatically scoring text's emotional polarity (positive/negative/neutral). This project
      uses NLTK's VADER (:term:`VADER`) for its ``sentiment``/``sentiment_variance`` fields.

   Subjectivity
      How much a text expresses personal opinion/feeling versus objective, factual statement,
      typically scored 0 (fully objective) to 1 (fully subjective). This project's ``subjectivity``
      field comes from TextBlob's sentiment module.

   VADER
      "Valence Aware Dictionary and sEntiment Reasoner" -- a lexicon-and-rule-based sentiment
      analysis tool tuned for short, informal text, used via NLTK's
      ``SentimentIntensityAnalyzer``. This project's sentiment metrics are computed with it, not a
      learned/neural sentiment classifier.

Computational linguistics and psycholinguistics
--------------------------------------------------------

.. glossary::
   :sorted:

   Type-Token Ratio (TTR)
      Unique words ("types") divided by total words ("tokens") in a text -- a classic lexical
      diversity measure, but one that shrinks predictably as text gets longer (more words means
      more chances to repeat one), making raw TTR unreliable for comparing texts of different
      lengths. This project reports both the raw version (``unique_ratio``) and a length-corrected
      version (``corrected_ttr``, dividing by ``sqrt(2 * word_count)``) side by side.

   Lexical density
      The proportion of *content* words (nouns, verbs, adjectives, adverbs) versus function/
      grammatical words in a text -- higher density is often associated with more information-dense,
      less conversational text. Computed here as non-stopword tokens / total word count.

   Lexical diversity
      The general concept :term:`Type-Token Ratio (TTR)` is one specific way of measuring --
      how varied a text's vocabulary is, as opposed to how much it repeats a small word set.

   Deixis / Deictic
      Language whose meaning depends on the context it's spoken in -- pronouns ("I," "you," "they"),
      here/there, now/then. This project's ``self_focus``/``social_focus`` metrics are a deictic
      contrast: first-person pronoun rate versus second/third-person pronoun rate.

   Hedging
      Language that marks uncertainty, tentativeness, or reduced commitment to a claim ("might,"
      "perhaps," "seems") -- one of Hyland's (2005) :term:`Metadiscourse` categories. This project's
      ``hedge_ratio`` field, a lexicon-ratio metric.

   Boosting (metadiscourse)
      Language that marks certainty or emphasis ("definitely," "always," "clearly") -- Hyland's
      (2005) counterpart category to :term:`Hedging`. This project's ``booster_ratio`` field.

   Metadiscourse
      Language that comments on the text itself or the speaker's stance toward it, rather than the
      subject matter directly -- Hyland's (2005) framework, of which :term:`Hedging` and
      :term:`Boosting (metadiscourse)` are two categories this project measures.

   Speech Act Theory
      A pragmatics framework (Searle) classifying utterances by what they *do* (directive,
      commissive, expressive, ...), not just what they literally say. Named in this project's own
      original feature wishlist but deliberately **not built** -- a naive rule-based classifier for
      this would be an uncalibrated guess, the exact class of mistake this project has already
      caught twice elsewhere (see :doc:`wiki/03-feature-implementation`'s tech-debt section).

   Gricean Maxims
      Grice's conversational principles (quality, quantity, relevance, manner) describing how
      cooperative communication is expected to behave -- violations are often meaningful (irony,
      evasion, manipulation). Also named in the wishlist, also **not built**, for the same
      calibration-risk reason as :term:`Speech Act Theory`.

   Pragmatics
      The study of how context shapes meaning beyond a sentence's literal content -- the broader
      linguistic field :term:`Speech Act Theory` and :term:`Gricean Maxims` both belong to.

   Readability
      How easy a text is to read and understand, typically approximated by sentence/word-length
      formulas rather than true comprehension testing. See :term:`Automated Readability Index
      (ARI)` for this project's specific formula.

   Automated Readability Index (ARI)
      A readability formula estimating US grade-level reading difficulty from character count,
      word count, and sentence count (``4.71 * chars/word + 0.5 * words/sentence - 21.43``). This
      project's ``readability_ari`` field. **Not the same metric as** :term:`Adjusted Rand Index
      (ARI)` -- see the callout at the top of this page.

   Zipf's law
      An empirical observation that in natural language, a word's frequency is roughly inversely
      proportional to its rank in a frequency table (the most common word appears ~2x as often as
      the second, ~3x the third, and so on). This project's ``zipf_deviation`` metric measures RMSE
      between a response's observed word-frequency curve and the curve Zipf's law would predict --
      the one metric in the whole linguistic-metric surface pinned against a hand-computed expected
      value in its own unit test.

Machine learning and statistics
------------------------------------

.. glossary::
   :sorted:

   Precision
      Of everything a classifier predicted positive, the fraction that was actually positive --
      answers "when it says yes, how often is it right." Reported by
      :class:`~core.analysis.model_evaluation.ModelEvaluation`'s classification report.

   Recall
      Of everything that was actually positive, the fraction the classifier correctly identified --
      answers "of all the real positives, how many did it catch." Reported alongside
      :term:`Precision`.

   F1 score
      The harmonic mean of :term:`Precision` and :term:`Recall`, balancing both into one number --
      useful when neither alone tells the full story (e.g. a classifier that predicts everything
      positive gets perfect recall but poor precision).

   ROC-AUC
      "Area Under the Receiver Operating Characteristic curve" -- a single number (0.5 = random
      guessing, 1.0 = perfect) summarizing a binary classifier's ability to rank positives above
      negatives across every possible decision threshold, not just one. Reported by
      ``/model_evo``'s baseline fit.

   Confusion matrix
      A table cross-tabulating a classifier's predicted labels against actual labels, showing
      exactly which classes get confused with which -- more informative than a single accuracy
      number. Rendered by ``/model_evo``.

   Logistic regression
      A linear model predicting a categorical outcome's probability from input features. This
      project's :class:`~core.analysis.model_evaluation.ModelEvaluation` fits one predicting a
      chosen label (e.g. ``archetype``, ``v_ok_numeric``) from the full linguistic-metric set -- a
      real, if simple, construct-validity check: do these metrics carry predictive signal at all.

   Feature importance
      A score for each input variable indicating how much it contributed to a fitted model's
      predictions. For :term:`Logistic regression`, this project reads the fitted coefficients
      directly -- which linguistic metrics actually predict the target label, and how strongly.

   Supervised learning
      Training a model on labeled examples (input, correct-output pairs) so it learns to predict
      the output for new inputs. :term:`Logistic regression` here is supervised; the
      :term:`Clustering` techniques below are not (they have no labels to learn from).

   Clustering
      Grouping data points by similarity with no predefined labels (*unsupervised* -- contrast
      :term:`Supervised learning`). This project's whole corpus-level confirmatory analysis
      (CLAUDE.md SS3b) is built on clustering linguistic-feature vectors and checking whether the
      resulting groups line up with the archetype labels chosen at generation time.

   K-means
      A clustering algorithm that partitions data into a chosen number (``k``) of groups by
      iteratively assigning points to the nearest of ``k`` cluster centers and recomputing those
      centers. This project's original :class:`~core.analysis.cluster_discovery.ClusterDiscovery`
      class (KMeans + PCA), distinct from the newer HDBSCAN-based workflow.

   Dimensionality reduction
      Projecting high-dimensional data (e.g. dozens of linguistic-metric columns) down to a much
      smaller number of dimensions, for visualization or to make downstream algorithms tractable,
      while trying to preserve the data's real structure. :term:`Principal Component Analysis
      (PCA)` and :term:`UMAP` are both dimensionality-reduction techniques, with very different
      goals.

   Principal Component Analysis (PCA)
      A linear dimensionality-reduction technique finding the directions ("components") of maximum
      variance in the data. Used in this project's original :class:`~core.analysis.cluster_discovery
      .ClusterDiscovery` (KMeans + PCA path) -- purely linear, preserves global variance structure
      rather than local neighborhood structure (contrast :term:`UMAP`).

   UMAP
      "Uniform Manifold Approximation and Projection" -- a non-linear dimensionality-reduction
      technique that preserves *local* neighborhood structure well, widely used ahead of density
      clustering. This project's Behavioral Topology workflow
      (:func:`core.services.cluster_discovery.run_behavioral_topology`) uses it twice: a 2D
      projection for visualization, and a separate, higher-dimensional one purely for feeding
      :term:`HDBSCAN` -- a deliberate split, since forcing both roles onto the same 2D projection
      distorts density.

   HDBSCAN
      "Hierarchical Density-Based Spatial Clustering of Applications with Noise" -- a clustering
      algorithm that finds clusters of varying density and explicitly labels sparse points as
      *noise* rather than forcing every point into some cluster (contrast :term:`K-means`, which
      always assigns every point). This project's primary clustering technique
      (:func:`core.services.cluster_discovery.run_plain_hdbscan`,
      :func:`~core.services.cluster_discovery.run_behavioral_topology`).

   Silhouette score
      A cluster-validity metric: for each point, how much closer it is to its own cluster than to
      the nearest other one, averaged over all points (roughly -1 to 1; higher is better-separated
      clusters). One of three metrics
      :func:`core.services.cluster_discovery.compute_fit_indices` reports as a construct-validity
      proxy.

   Davies-Bouldin index
      A cluster-validity metric comparing each cluster's internal spread against its separation
      from the nearest other cluster, averaged (lower is better -- opposite direction from
      :term:`Silhouette score`). Reported alongside it, with a legacy-matching sentinel value
      (``99.0``) when only one cluster exists and the index is undefined.

   Adjusted Rand Index (ARI)
      A cluster-validity metric measuring agreement between a clustering result and a known
      ground-truth labeling (here: the real ``archetype`` label), corrected for the agreement
      expected by chance alone (0 = chance-level agreement, 1 = perfect). This project's one
      *label-alignment* cluster metric, as opposed to Silhouette/Davies-Bouldin's *shape-only*
      metrics. **Not the same metric as** :term:`Automated Readability Index (ARI)` -- see the
      callout at the top of this page.

   Noise ratio / Outlier
      In density-based clustering (:term:`HDBSCAN`), the fraction of points that don't fit densely
      into any cluster and are explicitly labeled ``-1`` ("noise") rather than force-assigned. This
      project's ``noise_ratio`` field, and the "outliers" table in the Behavioral Topology view --
      a real, usable signal for CLAUDE.md's "noisy data" question, not a placeholder.

Project-specific terms
---------------------------

.. glossary::
   :sorted:

   Archetype
      This project's term for a target behavioral style a generated response should exhibit (e.g.
      "Detached," "Anxious," "Expressive") -- the primary independent variable the whole pipeline is
      built to condition generation on and then measure. Not a standard AI/ML term; specific to
      this project's design.

   Bias
      **This project's specific sense, not the general ML "training bias"/"model bias" sense.**
      A short, comma-separated list of style/tone tags (e.g. ``"personalization, formal, toxic"``)
      further conditioning a generation alongside :term:`Archetype`. Its tag-like (not
      natural-language) structure is exactly what drove the Layer 1 threshold-inversion finding --
      see :doc:`wiki/04-llm-analytics`'s "A real threshold had to be inverted" section for the full
      cause-and-effect story, and its own open question about whether the tag *content* (register,
      valence, lexical rarity) deserves its own validation.

   Behavioral conditioning
      This project's term for the overall technique: prompting an LLM to generate text exhibiting a
      target :term:`Archetype`/:term:`Bias` combination, then measuring how well it did and how
      that behavior shifts under different sampling parameters.

   Echo response / Echo detection
      This project's term for a specific real failure mode: the model repeating its own
      :term:`Bias` instruction back nearly verbatim instead of generating genuinely conditioned
      text. Detected by Layer 1 (:func:`core.analysis.response_classification.is_echo_response`) --
      the check that surfaced the threshold-inversion finding above.

   Cascade Layer 0
      The evaluation cascade's deterministic validity gate
      (:func:`core.analysis.response_classification.classify_response`) --
      ``VALID``/``EMPTY``/``MALFORMED_JSON``/``TRUNCATED``/``SCHEMA_ERROR``. See :term:`Cascade
      (evaluation cascade)`.

   Cascade Layer 1
      The evaluation cascade's :term:`Echo response / Echo detection` check, reusing
      ``semantic_overlap``. See :term:`Cascade (evaluation cascade)`.

   Cascade Layer 2
      The evaluation cascade's :term:`Natural Language Inference (NLI)`-based factual-contradiction
      check against :term:`Retrieval-Augmented Generation (RAG)` context -- real but deliberately
      non-gating (see :doc:`wiki/04-llm-analytics`). See :term:`Cascade (evaluation cascade)`.

   Cascade Layer 3
      The evaluation cascade's LLM judge call (:class:`~core.adapters.structured_judge
      .StructuredJudge`). See :term:`Cascade (evaluation cascade)`.

   Sweep (parameter sweep)
      Running the same :term:`Archetype`/:term:`Bias` combination repeatedly while varying one
      sampling parameter (:term:`Temperature`, :term:`Top-p (nucleus sampling)`, etc.) across a
      range of values, to observe how output behavior changes as that single dial turns. This
      project deliberately supports only one swept parameter per run at a time -- see
      :doc:`roadmap`'s Stage 6 entry for the combinatorial-cost reasoning behind that limit.
