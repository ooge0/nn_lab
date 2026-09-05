04 — LLM Analytics: What Is Actually Measured, and How Well
================================================================

This is the most detailed page in this wiki, deliberately -- CLAUDE.md's own stated differentiator
for this whole project is "measurement validity: proving a metric measures what it claims and that
the signal is not noise," not breadth of features. This page audits that claim directly against the
code: every metric this project computes, how they connect across levels of granularity, what
industry-standard LLM-evaluation technique is present versus genuinely absent, and what business
questions the system can and cannot yet answer with real evidence.

Metric inventory, by level of granularity
------------------------------------------------

Three independent modules compute per-response metrics, called back to back in
``ExperimentRunner._run_one`` (:doc:`03-feature-implementation` covers where this sits in the
pipeline):

.. code-block:: python

   sci = PsychScientist()
   neuro = NeuroMetrics(sci.sia)
   nlp_stats = sci.analyze_text(clean_text, result.duration_ms)
   neuro_stats = neuro.compute(clean_text)
   base_metrics_dict = calculate_advanced_linguistic_metrics(bias, clean_text, result.duration_ms).model_dump()

Token/phrase level -- computed per single response
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 22 40 38
   :header-rows: 1

   * - Metric (persisted key)
     - Source
     - What it measures
   * - ``sentiment``
     - :class:`~core.analysis.nlp_science.PsychScientist`, NLTK VADER ``polarity_scores`` compound
     - Overall polarity
   * - ``sentiment_variance``
     - Same, variance of per-sentence VADER compound scores
     - Emotional volatility across sentences
   * - ``subjectivity``
     - Same, ``TextBlob(text).sentiment.subjectivity``
     - Opinion vs. fact framing
   * - ``lexical_density``
     - Same, non-stopword tokens / word count
     - Content-word ratio
   * - ``corrected_ttr``
     - Same, ``unique_words / sqrt(2 * word_count)``
     - Length-corrected vocabulary diversity
   * - ``readability_ari``
     - Same, standard Automated Readability Index formula
     - Grade-level readability
   * - ``avg_sentence_length``
     - Same
     - Syntactic pacing
   * - ``self_focus``
     - Same, broad pronoun set (``i, me, my, mine, myself, we, us, our, ours, ourselves``) / word count
     - First-person reference rate -- **name collides with a second, narrower computation below**
   * - ``social_focus``
     - Same, second/third-person pronoun set (``you, he, she, they, ...``) / word count -- added
       2026-08-24
     - The deictic contrast ``self_focus`` was missing: I-focus vs. social-focus, now directly
       comparable rather than I-focus reported alone
   * - ``modality``
     - Same, 11-word modal-verb lexicon hit rate
     - Epistemic hedging/certainty
   * - ``hedge_ratio``
     - Same, epistemic-hedge lexicon (``might, perhaps, seem, possibly, ...``) hit rate -- added
       2026-08-24, Hyland (2005) metadiscourse framework
     - Tentativeness/uncertainty marking -- deliberately *not* a Speech Act or Gricean-maxim
       classifier, see :doc:`03-feature-implementation`'s tech-debt section for why those are
       different, harder problems left unbuilt
   * - ``booster_ratio``
     - Same, certainty-booster lexicon (``definitely, always, absolutely, ...``) hit rate -- added
       2026-08-24, same Hyland (2005) framework's counterpart to ``hedge_ratio``
     - Certainty/emphasis marking
   * - ``cognitive_density``
     - Same, cognitive-verb lexicon (``think``, ``believe``, ``analyze``, ...) hit rate
     - Metacognitive vocabulary use
   * - ``repetition_score``
     - Same, most-common-word count / word count
     - Lexical fixation (single dominant word only)
   * - ``abstract_ratio``
     - Same, WordNet hypernym heuristic (``"abstraction"``/``"entity"`` in a word's first hypernym)
     - Abstract vs. concrete language -- a heuristic, not validated against a lexical-norms dataset
   * - ``pos_distribution``
     - Same, NLTK POS-tag grouping into NOUN/VERB/ADJ/ADV
     - Morphological profile
   * - ``zipf_deviation``
     - Same, ``PsychScientist.zipf_deviation`` -- RMSE between the observed word-frequency-by-rank
       curve and Zipf's-law's expected curve, normalized
     - How naturally the vocabulary follows Zipf's law; the one metric in this table pinned against
       a hand-computed expected value on a fixed synthetic distribution
   * - ``self_focus_ext``
     - :class:`~core.analysis.neuro_metrics.NeuroMetrics`, narrower pronoun set (``i, me, my, mine, myself`` -- no we/us/our)
     - Same construct as ``self_focus`` above, deliberately renamed at the merge point -- see
       *A real, fixed data-loss bug* below
   * - ``rigidity``
     - Same, fraction of all tokens that are repeats of any earlier token
     - Structural fixation -- distinct from ``repetition_score``'s single-most-common-word framing
   * - ``sentiment_variance_ext``
     - Same, independently re-derives the variance-of-VADER-compound idea
     - Duplicate construct by design, intentionally ``_ext``-suffixed from the start
   * - ``abstract_ratio_ext``
     - Same, closed 8-word lexicon (``meaning, identity, existence, system, process, concept, structure, theory``)
     - A *different technique entirely* from ``abstract_ratio``'s WordNet approach, sharing only a name family
   * - ``modality_ext``
     - Same, closed 5-word lexicon (``must, should, always, never, definitely``)
     - Different lexicon from ``modality`` above (11 modal verbs vs. 5 adverbs/modals)
   * - ``cognitive_load``
     - Same, unweighted mean of average sentence length + punctuation density + subordinator ratio
     - A composite of sentence length, punctuation density, and subordinate-clause rate. Originally
       an unweighted average of three quantities on incompatible raw scales; fixed to normalize each
       component to ``[0, 1]`` before averaging -- see *A fixed normalization gap* below
   * - ``coherence``
     - Same, TF-IDF-vectorized sentences, mean adjacent-sentence cosine similarity
     - Local narrative coherence -- bag-of-words based, not a learned semantic embedding
   * - ``levenshtein_dist``
     - :func:`~core.analysis.calculate_advanced_linguistic_metrics.calculate_advanced_linguistic_metrics`,
       ``Levenshtein.distance`` between the *prompt/bias text* and the output
     - Character-edit distance from the input the model was given
   * - ``semantic_overlap``
     - Same -- **sentence-embedding cosine similarity** (``all-MiniLM-L6-v2``, the same model
       :mod:`core.adapters.rag.vector_store` uses), input vs. output
     - Genuine meaning-level similarity, not surface token overlap -- see *A fixed naming/technique
       gap* below for what this replaced
   * - ``expansion_ratio``
     - Same, output word count / input word count
     - Verbosity relative to the prompt
   * - ``word_count_raw`` / ``ms_per_word_raw``
     - Same, naive ``.split()`` tokenization
     - Renamed at the merge point -- collides with ``PsychScientist``'s NLTK-tokenized versions of
       the same names, see below
   * - ``punc_density``
     - Same, punctuation character count / word count
     - Punctuation rate
   * - ``unique_ratio``
     - Same, unique output words / word count
     - Type-token ratio, **uncorrected** -- contrast with ``corrected_ttr`` above, which length-corrects the same idea
   * - ``dependency_distance``
     - :mod:`core.analysis.syntactic_complexity`, spaCy + TextDescriptives'
       ``textdescriptives/dependency_distance`` pipe -- added 2026-08-24
     - Mean dependency-tree distance between syntactically related token pairs -- a validated
       complexity/intellectualization marker (Oakes 2017, Lu 2010), independent of raw sentence
       length. The only spaCy-based (not NLTK-based) computation in the per-response pipeline.
       CLAUDE.md SS7 names both ``textdescriptives`` and ``lexicalrichness`` as preferred libraries;
       neither had actually been wired into any code until this metric

Cross-response / model-comparison level
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``levenshtein_dist`` and ``semantic_overlap`` (both above) compare the model's output against the
  **prompt/bias text it was given**, not against a teacher model's own generated response. One
  analytics chart's title used to say "Levenshtein distance to teacher," implying otherwise -- fixed
  2026-08-24 to "Levenshtein distance to prompt/bias" (see *A metric that contradicted itself*
  below for the related, higher-stakes instance of the same gap in the benchmark leaderboard). No
  metric anywhere compares one model's response directly against another model's response for the
  same prompt; cross-model comparison happens only by grouping and aggregating each model's own
  per-response metrics.
- ``tokens_per_second`` -- ``completion_tokens / (ollama_eval_duration_ms / 1000)``, a real
  measurement derived from Ollama's own native per-call timing (:doc:`02-tools-and-stack` covers why
  the native API is used at all), contrasted deliberately against the ``ms_per_word`` proxy every
  backend can compute regardless of what telemetry it exposes.

Corpus / pipeline level
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Cluster fit indices** -- :func:`core.services.cluster_discovery.compute_fit_indices` calls
  scikit-learn's ``silhouette_score``, ``davies_bouldin_score``, and ``adjusted_rand_score`` (the
  last against the real ``archetype`` label as ground truth) directly, with legacy-matching
  sentinel values (``silhouette=0.0``, ``davies_bouldin=99.0``) when only one cluster exists and
  the indices are mathematically undefined. This is the one place in the whole metric surface that
  is genuinely pinned to an exactly-known correct answer in a unit test (two tight, far-apart
  synthetic clusters, silhouette expected ≈0.99, Davies-Bouldin ≈0.01) -- confirmed directly in
  ``tests/unit/test_cluster_discovery.py``, not just documented as tested.
- **Weighted benchmark leaderboard** -- ``web/plotting/benchmark_charts.py``'s ``final_score`` is a
  fixed linear combination, as of 2026-08-24: ``0.4 × pass_rate + 0.3 × coherence + 0.3 ×
  speed_score``. Until that date it also included a ``mimicry_score`` term -- see *A metric that
  contradicted itself: the leaderboard rewarded what Layer 1 rejects* below for why that was removed
  rather than fixed in place. The remaining weights are still hand-picked, with no cross-validation
  or sensitivity analysis behind them -- that part of the leaderboard design is unchanged.
- **Baseline predictive-signal check** -- :class:`~core.analysis.model_evaluation.ModelEvaluation`
  fits a ``LogisticRegression`` predicting a chosen label (typically ``archetype`` or
  ``v_ok_numeric``) from the full metric set, reporting precision/recall/ROC-AUC/confusion matrix
  and coefficient-based feature importance. This is a real construct-validity tool -- do the metrics
  carry any predictive signal for the label at all -- but it's a supervised model over the *same*
  hand-built metrics, not an independently-sourced validation signal.

How the levels connect
----------------------------

The three per-response modules feed one flat record per response; that record is the unit
everything above it aggregates over. Cross-response metrics (``tokens_per_second``,
``levenshtein_dist``) are computed at the same per-response step but only become meaningful when
compared across many rows, grouped by model/archetype/bias. Corpus-level analysis
(:doc:`03-feature-implementation` covers the pipeline) only exists once enough per-response records
have accumulated -- clustering, fit indices, and the benchmark leaderboard all read the *persisted*
corpus back out, they never touch a live in-progress run. This two-stage separation (per-response
cascade vs. corpus-level confirmatory analysis) is a named, deliberate architectural rule in
CLAUDE.md SS3, not an implementation detail -- the two stages must not be collapsed into one flow,
because clustering fundamentally needs the whole accumulated set to form clusters at all, while a
per-response verdict has to be decidable from one response alone.

A real, fixed data-loss bug -- twice, at two different merge points
------------------------------------------------------------------------

Two of the collisions in the table above (``self_focus``/``self_focus_ext``,
``word_count``/``word_count_raw``, ``ms_per_word``/``ms_per_word_raw``) are not just awkward naming
-- they were a genuine silent data-loss bug. ``PsychScientist`` and ``NeuroMetrics`` independently
compute ``self_focus`` under *different pronoun sets*; ``PsychScientist`` and
``calculate_advanced_linguistic_metrics`` independently compute ``word_count``/``ms_per_word`` under
*different tokenization* (NLTK vs. a naive whitespace split). The three metric dicts are merged with
plain sequential ``dict.update()`` calls, which silently let whichever dict updates last win on a
key collision -- observed directly, on real generated text, losing ``PsychScientist``'s more
accurate ``self_focus`` value in favor of a wrong ``0.0`` from ``NeuroMetrics``' narrower pronoun
set. The fix renames the losing side at the merge point (``_ext``/``_raw`` suffixes, matching a
convention ``NeuroMetrics`` already applied to six of its other seven overlapping fields, just not
this one).

**A second, independent instance of the identical defect class** was found one layer downstream, in
:mod:`core.analysis.data_contract`'s ``LabDataBridge.transform_raw`` -- the field-mapping logic
feeding the ``/nlp`` page specifically (which loads data through a different path than the other
analytics pages, see :doc:`03-feature-implementation`). Its mapping preferred the bare, un-suffixed
``self_focus``/``sentiment_variance`` keys, an assumption that happened to be harmless only for
pre-fix exports (where the dict-merge collision above had already resolved to one winner) -- on
current, correctly-merged data it was silently mislabeling ``PsychScientist``'s value as
``neuro_self_focus``. Two independently-discovered instances of the same underlying defect class,
each fixed at its own merge point, is real evidence the project's "measurement validity" claim is
being actively exercised against the code, not just stated as an intention.

A fixed naming/technique gap: ``semantic_overlap`` used to not be semantic
--------------------------------------------------------------------------------

Found during the audit this wiki page itself is built from, and fixed directly rather than just
documented: the field named ``semantic_overlap`` was computed as a plain Jaccard index over
lowercased, whitespace-split token sets -- ``len(intersection) / len(union)`` of the input and
output word sets. No embedding model, no cosine similarity in a learned vector space, nothing
"semantic" about it in the sense the field name implies -- the function's own docstring cited
"Jaccard similarity" as one of its own references in the same breath as the field name
``semantic_overlap``, suggesting the gap between name and technique had never actually been
scrutinized. This is exactly the kind of construct-validity problem CLAUDE.md's own framing exists
to catch: a metric that looks like it measures meaning-level similarity, but actually measures
surface token overlap, silently overstates how much semantic fidelity the pipeline is verifying
wherever the field feeds a downstream number -- including, as it turned out, the benchmark
leaderboard's former ``mimicry_score`` (see the dedicated section below for how that specific
downstream consumer broke once this fix landed).

**Fixed**: :func:`~core.analysis.calculate_advanced_linguistic_metrics.calculate_advanced_linguistic_metrics`
now computes ``semantic_overlap`` as a real sentence-embedding cosine similarity, via a lazily-loaded
``all-MiniLM-L6-v2`` :class:`~sentence_transformers.SentenceTransformer` -- the same model
:mod:`core.adapters.rag.vector_store` already uses for RAG retrieval, reused rather than adding a
second embedding model to the dependency footprint. This is a genuine behavior change, not a
comment-only fix: every future run's ``semantic_overlap`` values now measure something different
(and construct-valid) from what earlier runs' exported JSONL files contain -- worth knowing when
comparing a new run's benchmark numbers against an older export. Pinned in
``tests/unit/test_calculate_advanced_linguistic_metrics.py``: near-paraphrase sentence pairs
(zero shared words) score a high similarity, genuinely unrelated pairs score low, and the function
is clamped to ``[0, 1]`` since raw cosine similarity can be slightly negative for real embeddings.

The other embedding-adjacent technique in the metric surface, ``coherence``, still uses TF-IDF
vectors (a bag-of-words weighting, not a learned embedding) and measures intra-response sentence
coherence, not cross-response similarity to anything -- that one is unchanged, since it answers a
genuinely different question (internal narrative consistency) than ``semantic_overlap`` does
(fidelity to the input).

A fixed normalization gap: ``cognitive_load``'s composite now weighs all three components
------------------------------------------------------------------------------------------------

Also found during this same audit and fixed: :meth:`~core.analysis.neuro_metrics.NeuroMetrics.cognitive_load`
averaged three quantities on incompatible raw scales -- sentence length (commonly 5-30+ words) and
two already-``[0, 1]`` ratios (punctuation density, subordinate-clause rate) -- with no normalization
step first. Averaging them unnormalized let sentence length's raw magnitude dominate the composite,
making the other two components nearly irrelevant to the final number regardless of how punctuation-
or subordination-heavy a response actually was. This wasn't a crash or a wrong-type bug -- the
function always returned a valid float -- it was a methodological flaw invisible to any test that
only checks "does this return a number."

**Fixed**: each component is now min-max normalized to ``[0, 1]`` before averaging. Sentence length
is capped at 40 words/sentence (a chosen, disclosed "very long sentence" threshold, not an
empirically-derived one -- the same honesty standard already applied to ``abstract_ratio``'s WordNet
heuristic); punctuation density is clamped defensively, since a very short, heavily-punctuated
response can otherwise exceed 1.0 (more punctuation characters than words); subordinate-clause rate
was already naturally bounded and needed no change. Like the ``semantic_overlap`` fix, this changes
real output values relative to earlier exports, not just the code's internals. Pinned in the newly
created ``tests/unit/test_neuro_metrics.py`` -- including a hand-computed exact expected value
(``0.2``, worked out by hand on a fixed 4-word/1-subordinator/1-punctuation-mark input) and a
saturation test confirming the 40-word cap actually caps rather than merely existing in a comment.

A metric that contradicted itself: the leaderboard rewarded what Layer 1 rejects
--------------------------------------------------------------------------------------

Found 2026-08-24, directly caused by the ``semantic_overlap`` fix above landing correctly while a
downstream consumer was never re-examined against its new meaning. ``web/plotting/benchmark_charts.py``'s
``/benchmark`` leaderboard computed ``mimicry_score = semantic_overlap × 100`` and weighted it 30%
into each model's ``final_score`` -- named "teacher-mimicry" in both the module and the rendered
page (``web/templates/_benchmark_report.html``), implying it measured how closely a student's output
resembled a teacher model's reference response. It did not: as *Cross-response / model-comparison
level* above already states, ``semantic_overlap`` (like ``levenshtein_dist``) compares the response
against the **bias/archetype label**, not against any teacher output -- no field anywhere in the
persisted schema compares one model's response to another model's response for the same prompt.

That naming gap alone would have been worth fixing on its own -- but it became an active
contradiction, not just an inaccurate label, once ``semantic_overlap`` became the real embedding
value CLAUDE.md SS4's Layer 1 fix (see :doc:`06-qa-testing-strategy` and the cascade section below)
also reuses: :func:`core.analysis.response_classification.is_echo_response` rejects a response
specifically **because** its ``semantic_overlap`` is high -- that is the project's own, calibrated
signal for "the model echoed its bias/archetype instruction back instead of generating real
conditioned text" (see *A real threshold had to be inverted*, below). The benchmark leaderboard was
rewarding models with **higher** ``final_score`` for exactly that same high-``semantic_overlap``
behavior, in direct opposition to what the cascade had just been built to reject. A model that
echoed its instructions more often, all else equal, would have ranked *better* on the leaderboard's
own "teacher-mimicry" dimension -- the kind of internal metric disagreement this project's whole
"measurement validity" framing (CLAUDE.md SS0) exists to catch before it goes unnoticed.

**Fixed**: ``mimicry_score`` removed from ``final_score`` entirely, rather than pointed at a
different (still-unvalidated) proxy field -- no genuine "closeness to teacher" metric currently
exists in the schema to replace it with honestly. ``final_score`` is now
``0.4 × pass_rate + 0.3 × coherence + 0.3 × speed_score``, over the three signals that were already
independently real. The rendered page's "teacher-mimicry" wording was removed from
``_benchmark_report.html`` and ``features.rst`` alongside the code change, not left describing a
dimension that no longer exists. A related, separately-mislabeled chart title
(``web/plotting/analytics_charts.py``'s "Levenshtein distance to teacher" bar, flagged but not yet
fixed at the time the *Cross-response / model-comparison level* section above was first written) was
corrected in the same pass, to "Levenshtein distance to prompt/bias" -- the same underlying
field-meaning gap, caught the first time in a chart label, caught the second time as an actual
scoring contradiction.

What is built of the intended evaluation cascade, and what is not
--------------------------------------------------------------------------

CLAUDE.md SS3a specifies a four-layer per-response cascade: deterministic gates, then STS
embeddings, then NLI/specialized classifiers, then a generative judge, in that order, with routing
that is static and deterministic rather than LLM-orchestrated. As of **2026-08-24**, all four layers
have real, working code behind them for the first time, following a direct code-review pushback
from the author (see :doc:`06-qa-testing-strategy` for the exact review that triggered this) and one
narrow, explicit exception CLAUDE.md SS6 records to its own "author writes the moat" rule -- not a
general lifting of that rule. Layer 2 is the one still qualified: real and tested as a mechanism,
but deliberately not yet trusted as a rejection gate (see below). What follows is the state *before*
that date (for the historical record) and *after*.

**Before 2026-08-24:** checked directly against the code, **there was exactly one judge call site in
the entire pipeline**, and it routed straight through ``NaiveJudge`` -- no orchestrator, no earlier
layer, nothing for a router to route *between*. ``ExperimentRunner._run_one`` carried its own
standing comment marking precisely where Layer 0 validity classification belonged, and stated
plainly: "today this seam passes everything through unfiltered." The judge itself was the same
fragile mechanism CLAUDE.md SS4 names as the single most load-bearing, most fragile piece of the
whole system: it asked for structured JSON output (``json_mode=True``) but never parsed the response
as JSON -- it checked whether the literal substring ``"true"`` appeared in the lowercased response
text. A malformed, truncated, or entirely non-JSON response (an HTML error page, say) silently
became ``verdict=False``, indistinguishable from a genuine "no." ``JudgeVerdict.confidence`` and
``.rationale`` existed as schema fields but were confirmed, by direct code read, to never be
populated.

**As of 2026-08-24:**

- **Layer 0** (:func:`core.analysis.response_classification.classify_response`) is built: a pure,
  model-free classification of the raw response -- ``VALID``/``EMPTY``/``MALFORMED_JSON``/
  ``TRUNCATED``/``SCHEMA_ERROR`` -- run in ``ExperimentRunner._run_one`` *before* any metric or
  judge call. A non-``VALID`` result short-circuits both. 5 of CLAUDE.md SS1's 7 classes are covered
  (``API_ERROR``/``FORMAT_ERROR`` are not -- see the module's own docstring for why: a real
  transport failure already surfaces as an exception before a response ever reaches this function,
  and ``FORMAT_ERROR`` isn't syntactically distinguishable from the others).
- **Layer 1** (:func:`core.analysis.response_classification.is_echo_response`) is built, but
  narrowly -- not the general topical-proximity gate CLAUDE.md SS3a's "STS embeddings" name implies.
  It flags one specific, real, previously-undetected failure mode: the model echoing its own
  archetype/bias instruction back instead of generating conditioned text (CLAUDE.md SS0's
  empirically-confirmed judge gap -- 7/125 real outputs in the original audit). It reuses
  ``semantic_overlap`` (see *A fixed naming/technique gap* above) rather than computing a second
  embedding comparison.
- **Layer 3** (:class:`~core.adapters.structured_judge.StructuredJudge`, replacing ``NaiveJudge``)
  now genuinely parses the judge's ``{verdict, confidence, rationale}`` JSON. A malformed response
  resolves to a *distinguishable* ``rationale`` ("...not valid JSON...") instead of a silent false
  negative, and ``confidence``/``rationale`` are populated when the judge model supplies them --
  left ``None``, not faked, when it doesn't.
- **Layer 2** (NLI/sentiment/toxicity classifiers) was **partially built later the same day**:
  :func:`core.analysis.hallucination_check.check_hallucination` is a real local NLI cross-encoder
  check against RAG-retrieved context, wired into ``ExperimentRunner._run_one`` -- but only runs
  when RAG is enabled, and is deliberately **non-gating** (persists a real predicted label and
  contradiction score, does not touch ``v_ok``). No real-data calibration exists yet for a rejection
  threshold, unlike Layer 1's -- see the dedicated section below for the full reasoning. Sentiment/
  toxicity classifiers remain entirely unbuilt. Still substantially the author's to hand-write and
  calibrate, per CLAUDE.md SS6 -- this is a mechanism, not a finished, trustworthy gate.

Cross-model judging *is* structurally supported and tested (the judge model can be the student
itself in self-critic mode, or a distinct teacher model otherwise), but no code anywhere computes or
logs the self-critic-vs-cross-model pass-rate delta CLAUDE.md SS4 calls for "at minimum" -- the
routing exists, the comparison it was meant to enable still does not.

Why Layer 2 logs a real score but does not reject anything (yet)
--------------------------------------------------------------------------

A real, working NLI mechanism is one thing; trusting a specific numeric threshold on it to reject
responses is another, and the two were deliberately not shipped together. Layer 1's own history
(below) is the direct cause of this caution: the first design attempt for Layer 1's threshold
*direction* was wrong, caught only because it was calibrated against real data before being trusted.
Layer 2 has had no equivalent calibration pass -- no corpus of real, RAG-enabled runs has been
generated and reviewed to confirm what a reasonable "reject as hallucinated" contradiction-score
cutoff actually looks like on this project's own data, the same way 0.5 was confirmed (not assumed)
as the right cutoff for Layer 1's echo detector.

Shipping an uncalibrated rejection threshold here would not be a neutral placeholder -- it would
silently start rejecting or accepting real responses based on a number nobody has verified means
what it's assumed to mean, exactly the failure mode CLAUDE.md's "measurement validity" framing
(SS0) exists to prevent. So Layer 2, as shipped, is a genuine, real capability with a real, honestly
reported score -- but it is presentation and data-collection infrastructure for the calibration step
that has to happen *before* a threshold is trustworthy, not the threshold itself. The `argmax`
predicted label (``contradiction``/``entailment``/``neutral``) and the raw ``contradiction_score``
are both persisted specifically so the author can review a batch of real RAG-enabled runs and decide
where a real cutoff belongs, the same process Layer 1 already went through.

A real threshold had to be inverted -- testing showing the opposite of the first assumption
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The first design attempt for Layer 1 assumed standard STS intuition: **low** similarity between the
response and the bias/archetype text means the response is off-topic, so reject low scores. Before
writing that into code, it was calibrated against real generated data
(``results/lab_experiment_results/*.jsonl`` -- real Ollama output, not synthetic examples), and the
calibration showed this assumption was backwards for this specific task:

- genuine, substantive archetype-conditioned responses scored ``semantic_overlap`` **0.06-0.30**
- confirmed echo failures (the model repeating its own bias/instruction back) scored
  ``semantic_overlap`` **0.59-0.98**

**Значит порог должен быть перевёрнут: Layer 1 отклоняет ВЫСОКОЕ сходство (эхо), а не низкое.**
("So the threshold has to be inverted: Layer 1 rejects HIGH similarity -- an echo -- not low.")

The cause-and-effect chain, not just the observation: this project's ``bias`` field is not a
natural-language prompt to be answered or paraphrased -- it is a short, comma-separated list of
style/tone **tags** (e.g. ``"personalization, formal, toxic"``), structurally closer to categorical
labels than to prose. A sentence-embedding model reads a long, substantive, on-topic response as
naturally *distant* from that terse tag string in embedding space -- different length, different
structure, different content entirely, since the response is *about* the tags rather than a
rewording of them. Echoing collapses that distance to near-zero, because the echo *is*, almost
verbatim, the tag string itself. The standard "low similarity = off-topic" intuition holds for
prompt/answer pairs where a good answer stays close to the question; it does not hold here, where
the "prompt" is a label, not a question. Reversing the threshold direction (reject **high**
similarity, not low) is a direct, correct consequence of that cause -- not an arbitrary flip. This is
a concrete, verified example of testing surfacing the *opposite* conclusion from the naive first
assumption, caught by calibrating against real data before writing the check, not after it shipped
wrong -- exactly the discipline CLAUDE.md's "measurement validity" framing (SS0) calls for. The
exact threshold, ``0.5``, sits in the wide, clean gap between the two observed clusters above; both
the classes and this rationale are pinned in
``core/analysis/response_classification.py::is_echo_response``'s calibration comment and in
``tests/unit/test_response_classification.py``'s Layer 1 tests.

**Open question, explicitly not resolved here.** The tag-like structure found above is one concrete
data point about the ``bias`` field's *length and syntax* -- it is not a general theory of what
"bias" is or should be, and it says nothing about the field's actual linguistic *content*. Whether
other properties of that content -- style/register, emotional valence, lexical rarity, or other
neurolinguistic dimensions the archetype-conditioning design leans on -- deserve their own dedicated
validation is a genuinely open question this project has not investigated. This matters because the
author's own words on this, verbatim: the bias-content design "typa staralsya" (roughly, "I did try,
but") sits in neurolinguistics territory the author does not have deep background in -- an
acknowledged, unpolished field of knowledge, not a solved one. Flagged honestly here as unexplored
territory precisely so a real, potentially important lesson about what ``bias`` content should
contain is not silently lost the way the threshold-direction assumption almost was -- not guessed
at, and not quietly folded into the fix above as if it were the same question.

The **corpus-level half of the cascade (CLAUDE.md SS3b) is genuinely built and live**, not just
designed: UMAP dimensionality reduction, HDBSCAN clustering, and the fit-index math described above
are real, reachable via ``/clusters``, and tested -- with an honest, explicitly-documented limit that
exact cluster-ID assignment isn't pinned in tests (non-deterministic across library versions even
with a fixed seed), while the deterministic math (``compute_fit_indices`` itself) is.

Coverage against industry-standard LLM-evaluation technique
--------------------------------------------------------------------

.. list-table::
   :widths: 30 12 58
   :header-rows: 1

   * - Technique
     - Present?
     - Notes
   * - BLEU / ROUGE
     - No
     - No reference-based n-gram overlap metric exists anywhere in the codebase.
   * - Perplexity
     - No
     - Would require model log-probabilities; ``GenerationResult`` (the domain entity every
       generation call returns) has no logprob field at all -- text, timing, and token *counts*
       only, never per-token probabilities.
   * - Embedding / semantic similarity
     - Yes
     - ``semantic_overlap`` is now a real sentence-embedding cosine similarity (see *A fixed
       naming/technique gap* above) -- it originally computed Jaccard token overlap under this
       field name, found and fixed during this same audit. ``coherence`` remains TF-IDF-cosine,
       not a learned embedding, since it answers a different question (intra-response coherence,
       not cross-text similarity). As of 2026-08-24 the embedding model is also used as a real
       cascade routing gate -- Layer 1's echo detector (see *A real threshold had to be inverted*
       below) -- though narrowly, for echo detection against the bias label only, not as a general
       topical-relevance gate against the full archetype/prompt.
   * - LLM-as-judge
     - Partial
     - Present, in single-sample form -- as of 2026-08-24 with genuine structured-JSON output
       (``StructuredJudge``, see above), not the earlier substring-matched form. No self-consistency
       or multi-sample voting exists (exactly one ``generate()`` call per verdict). Cross-model
       judging is structurally supported and tested, but the pass-rate-delta comparison it exists
       to enable is not computed anywhere.
   * - Human-in-the-loop annotation
     - No
     - No UI, form field, or data structure anywhere lets a human label or correct a response.
   * - Inter-annotator agreement / calibration tracking
     - No
     - Would only become meaningful once human annotation exists at all; explicitly named as future
       work in :doc:`../qa`'s own "Scaling the QA practice" section, not silently absent.
   * - Construct-validity checks
     - Yes
     - The one area that is a genuine, implemented strength, not a gap. ``compute_fit_indices``'s
       own docstring frames Silhouette/Davies-Bouldin/ARI explicitly as "construct-validity
       proxies, not a pass/fail judgment" -- the logic being: if behavioral archetypes are a real,
       measurable construct rather than a labeling fiction, clustering the linguistic feature
       vectors *should* recover structure aligned with the archetype labels. A high ARI is real
       evidence the archetype-conditioning prompts produce linguistically distinguishable text; a
       low ARI alongside acceptable Silhouette would instead suggest real structure exists but
       tracks something other than the intended labels. This is the differentiator CLAUDE.md SS0
       claims, implemented as real, tested code rather than left as an aspiration.

Concrete business cases: answerable today vs. not yet
------------------------------------------------------------

**Answerable today, with real evidence:**

- *Is a model's output linguistically distinguishable by archetype label, and is that structure
  real rather than noise?* -- ``/clusters``' Behavioral Topology view, via the fit-index math above.
- *Does one model pass the judge more often than another?* -- ``/benchmark``'s pass-rate chart and
  weighted leaderboard, real and reachable, and (as of 2026-08-24) backed by a judge that genuinely
  parses its own verdict rather than substring-matching ``"true"``.
- *Which specific linguistic dimension differs between two models or archetypes?* -- ``/nlp`` and
  ``/analytics``'s per-metric charts, reading real persisted values.
- *Do these metrics carry any predictive signal for the archetype/pass-fail label at all?* --
  ``/model_evo``'s logistic-regression baseline, with real precision/ROC-AUC and coefficient-ranked
  feature importance, not a placeholder.
- *Did the model just echo its own instruction back instead of generating real conditioned text?*
  -- Layer 1's echo detector, confirmed live against real Ollama output; see the threshold-inversion
  finding above for why the check looks the way it does.
- *How confident is the judge in a given verdict, and why did it decide that way?* --
  ``JudgeVerdict.confidence``/``.rationale`` are now genuinely populated by ``StructuredJudge`` when
  the judge model supplies them (left ``None``, not faked, when it doesn't).
- *Is a malformed, empty, truncated, or schema-broken response being scored differently from a
  genuine content failure?* -- partially: Layer 0 classifies 5 of CLAUDE.md SS1's 7 classes
  (``API_ERROR``/``FORMAT_ERROR`` excluded, see above) before either metrics or the judge run.
- *Is a response factually contradictory to the RAG context it was given?* -- partially, and
  logging-only: Layer 2's NLI cross-encoder gives a real contradiction score whenever RAG is
  enabled, but nothing rejects a response on it yet -- see *Why Layer 2 logs a real score but does
  not reject anything (yet)* above for why that gap is deliberate, not an oversight.

**Not yet answerable, specifically:**

- *Should a response be automatically rejected for contradicting its RAG context?* -- Layer 2 logs
  the signal (see above) but does not act on it; no real-data calibration exists yet for a rejection
  threshold, and sentiment/toxicity classifiers (the rest of CLAUDE.md SS3a's original Layer 2
  description) remain entirely unbuilt.
- *Is a response topically on-target against the full archetype/prompt, not just the bias label,
  before spending a generative-judge call on it?* -- Layer 1 only checks similarity to the terse
  bias string (deliberately narrow, an echo-detector, not a general relevance gate); no check
  compares the response to the fuller archetype/prompt content.
- *Is self-critic judging inflating pass rates relative to cross-model judging?* -- the routing to
  test this exists; the comparison itself is not computed or logged anywhere yet.
- *Has a human ever confirmed any verdict is actually correct?* -- no human-annotation surface
  exists; every "ground truth" in the system today is either the archetype label chosen at
  generation time, or the judge's own verdict.
- *Does the ``bias`` field's actual linguistic content -- register, valence, lexical rarity -- carry
  meaningful signal beyond its tag-like structure?* -- genuinely open, not investigated; see the
  open-question note above.
