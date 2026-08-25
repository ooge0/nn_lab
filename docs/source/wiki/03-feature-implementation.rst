03 — Feature Implementation: Data Flow and Known Debt
=========================================================

:doc:`01-architecture` establishes the mechanism (layers, threading, SSE). This page walks the two
features that mechanism actually serves, as data flows, and then names the real technical debt and
duplication in the current tree plainly -- not to apologize for it, but because a project whose
whole premise is measurement honesty should audit itself with the same standard.

Out of scope for this page, on purpose: the Neo4j knowledge-graph subsystem
(``core/service/neo4j_service.py``, ``core/tabs/knowledge_graph.py``,
``run_knowledge_graph.py``) is explicitly excluded from the FastAPI rewrite by CLAUDE.md SS1 --
"not ported, not adapted, not even import-path-touched." It is a real, still-running part of the
application, but not part of the architecture this wiki is documenting.

Feature: generating and judging a conditioned response
--------------------------------------------------------------

This is the system's core loop, and every other feature in the app is downstream of what it
persists. One iteration of the grid ``ExperimentRunner`` walks (:doc:`01-architecture` covers the
threading/SSE mechanism this runs inside) does, in order:

1. **Prompt construction.** :class:`~core.adapters.prompt_strategy.NaivePromptStrategy` builds the
   system prompt from the archetype/bias pair and the selected mode (Tuned / Blind / Raw). If RAG is
   enabled for the run, :class:`~core.domain.interfaces.KnowledgeBase` (concretely
   :class:`~core.adapters.rag.knowledge_base.RAGKnowledgeBase`) retrieves archetype-relevant chunks
   from ``knowledge/rag/`` first and folds them into the prompt -- this is the one place the lazy
   ``SentenceTransformer``-backed singleton from :doc:`01-architecture` gets used.
2. **Generation.** :class:`~core.adapters.ollama_client.OllamaClient` calls Ollama's native
   ``/api/chat`` for the selected student model, at the run's base sampling parameters or, for a
   swept parameter, that iteration's specific value (``compute_sweep_range`` resolves the actual
   value list once per run, not per call). The response includes real token counts and a
   load/prompt-eval/generation timing breakdown from Ollama itself, not just wall-clock duration.
3. **Extraction.** ``extract_best_text`` pulls the model's intended output out of the (requested,
   not guaranteed) JSON envelope, falling back to the raw text if the model didn't actually return
   valid JSON -- a real, expected failure mode this function absorbs rather than crashing on.
4. **Layer 0 gate.** :func:`core.analysis.response_classification.classify_response` classifies the
   extracted text as ``VALID``/``EMPTY``/``MALFORMED_JSON``/``TRUNCATED``/``SCHEMA_ERROR`` *before*
   any metric or judge call. A non-``VALID`` result short-circuits the rest of this list entirely --
   a minimal entry is persisted and the loop moves to the next task. Added 2026-08-24 (CLAUDE.md
   SS1's classification requirement); before that, every response reached the metrics and judge
   call unfiltered.
5. **Metric computation.** Three independent modules each compute a distinct set of linguistic/
   psycholinguistic metrics over the extracted text (``VALID`` responses only, per step 4). See
   :doc:`04-llm-analytics` for the full, per-metric inventory -- that page is where this project's
   actual measurement-validity work lives.
6. **Layer 1 gate.** :func:`core.analysis.response_classification.is_echo_response` reads step 5's
   own ``semantic_overlap`` value and rejects the response if it's *implausibly high* -- a sign the
   model echoed its own bias/archetype instruction back instead of generating conditioned text. The
   threshold direction (reject high, not low) is the inverse of standard STS intuition; see
   :doc:`04-llm-analytics` for the calibration finding that caught this before it shipped wrong. An
   echo synthesizes a rejection ``JudgeVerdict`` and skips step 7 entirely.
7. **Judging.** :class:`~core.adapters.structured_judge.StructuredJudge` -- reached only for a
   ``VALID``, non-echo response -- asks a model (the student itself in self-critic mode, or a
   separate teacher model otherwise) whether the response satisfies the archetype/bias it was
   conditioned on, and genuinely parses the ``{verdict, confidence, rationale}`` JSON it returns.
8. **Persistence and progress.** The merged record (now including
   ``layer0_classification``/``layer1_echo_detected``/``v_confidence``/``v_rationale``) is appended
   to the run's JSONL file, and a ``RunProgressEvent`` is bridged to whoever is watching the SSE
   stream.

**Each of these eight steps is a place engineering work has landed, at two different levels of
authorship.** CLAUDE.md's framing is that the author hand-writes the judge/cascade *decision logic*
(what step 4/6/7 actually decide is right or wrong), while the surrounding orchestration (steps 1-3,
8, and the plumbing of 4-7 into the right order) is this rewrite's engineering work. As of
2026-08-24, CLAUDE.md SS6 records two narrow, explicit exceptions crossing part of that boundary:
the AI agent built step 4 (Layer 0) and a narrow step 6 (Layer 1, echo-detection only) at the
author's direction, and fixed step 7's JSON-parsing bug -- but did not touch the judge's own
pass/fail *criteria* (still whatever the underlying LLM decides). Later the same day, a second
exception added a real but deliberately non-gating NLI check (against RAG context only) to cascade
Layer 2 -- see :doc:`04-llm-analytics`'s "Why Layer 2 logs a real score but does not reject anything
(yet)" section for why it stops short of a finished gate; sentiment/toxicity classifiers, the rest
of Layer 2's original scope, remain unbuilt, still the author's to write.
See CLAUDE.md SS4 for the permanent record of exactly what changed and what didn't.

Feature: corpus-level analysis and chart building
--------------------------------------------------------

Once a run has accumulated persisted responses, five read-side routers (``analytics``, ``nlp``,
``clusters``, ``model_evo``, ``benchmark``) each pull that run's JSONL back into a ``pandas``
DataFrame and build a page's worth of charts from it. Two genuinely different data-loading paths
exist here, not by accident: most routers load raw responses via plain ``pandas.json_normalize``,
while ``/nlp`` specifically goes through :class:`~core.analysis.data_contract.LabDataBridge`, which
normalizes every field through a validated ``LabSchema`` first (every field defaulted, so a
partial/legacy export never crashes a chart that expects a field an older run didn't persist).

The clustering pipeline is the most involved of the five, and the clearest example of *not*
building more than was decided on: the legacy Streamlit tab this was ported from contained **three
overlapping implementations** of the same UMAP+HDBSCAN+fit-index workflow (confirmed by literally
counting calls -- ``UMAP()`` invoked 4 times, ``HDBSCAN()`` 4 times, each fit-index function 3
times, inside one 1307-line tab). Only the most complete of the three ("Behavioral topology") was
ported forward into :mod:`core.services.cluster_discovery`; the other two were left behind
deliberately, the same way an earlier duplicate ``data_contract_old.py`` was retired rather than
carried forward unexamined. What *did* get built is real: two UMAP fits at different dimensionality
(one 2D purely for visualization, a separate higher-dimensional one actually feeding HDBSCAN,
because collapsing both onto one 2D projection distorts density), followed by the fit-index math
:doc:`04-llm-analytics` covers in detail.

Chart rendering itself splits across two libraries for a real technical reason (HDBSCAN's own
diagnostic plots have no Plotly equivalent), not two competing conventions -- see
:doc:`01-architecture`'s frontend section for the full explanation.

Known technical debt and duplication -- named plainly
--------------------------------------------------------------

- **``SQLiteRepo`` is a complete, tested, unused second ``Repository`` implementation** -- see
  :doc:`01-architecture`'s architecture-patterns section for the full story. Flagged again here
  specifically as debt, not just as a pattern: the wiring to actually use it for what it was built
  for -- avoiding the ~21% run-metadata duplication a real exported JSONL file was measured to
  contain -- simply hasn't landed.
- **Six routers each construct their own ``JSONLStore()`` instance** (``runs.py``, ``analytics.py``,
  ``clusters.py``, ``model_evo.py``, ``benchmark.py``, ``nlp.py``) rather than sharing one. The class
  is close to stateless (a small in-memory path cache aside), so this isn't a correctness bug, but
  it's the direct, visible cost of not using FastAPI's ``Depends()`` system described in
  :doc:`01-architecture`: there's no shared container to construct it once and hand it to every
  router that needs it.
- **A metric-name collision that was a real, silent data-loss bug, not just a naming clash.** Two
  separate modules independently compute constructs sharing a key name -- ``self_focus`` (two
  different pronoun sets) and ``word_count``/``ms_per_word`` (NLTK tokenization vs. a naive
  whitespace split) -- and a plain sequential ``dict.update()`` merge silently let whichever
  computation ran last overwrite the other. This was found and fixed at the merge point (renaming
  the losing side with an ``_ext``/``_raw`` suffix, matching a convention already used for six other
  overlapping fields) -- but a **second, independent instance of the identical defect class** was
  found later, one layer downstream, in :mod:`core.analysis.data_contract`'s own field-mapping logic
  for the ``/nlp`` read path specifically. See :doc:`04-llm-analytics` for exactly which fields this
  affects and why it matters for measurement validity, not just data hygiene.
- **The Layer-0/Layer-1 validity-classification seam was named in code but not filled -- resolved
  2026-08-24.** CLAUDE.md SS1 calls for classifying every response
  (``VALID``/``MALFORMED_JSON``/``TRUNCATED``/etc.) *before* the metric-computation step described
  above -- computing full linguistic metrics on a response that turns out to be empty or truncated
  wastes real, measured-as-costly compute for no signal. This is no longer a gap: Layer 0
  (:func:`core.analysis.response_classification.classify_response`) and a narrow, embedding-based
  Layer 1 (:func:`core.analysis.response_classification.is_echo_response`) are both built and wired
  into ``ExperimentRunner._run_one`` ahead of metrics and the judge call, by one narrow, explicit
  exception to CLAUDE.md SS6's author-writes-the-moat rule. Cascade Layer 2 (NLI/sentiment/toxicity
  classifiers) remains the one still-unfilled seam. See :doc:`04-llm-analytics` for the full
  picture, including a real threshold-inversion finding from calibrating Layer 1 against this
  project's own data.
- **A stray, untracked-workflow ``requirements.txt`` duplicates ``requirements-base.txt`` under a
  different, undocumented name.** Found while reviewing this section: the repo root has both a
  git-tracked ``requirements.txt`` (421 lines, last touched 2026-06-22) and the actively-maintained
  ``requirements-base.txt`` (555 lines) -- but only the latter appears anywhere in CLAUDE.md SS11's
  documented ``pip-compile`` commands, the README's "Dependency Architecture" section, or this
  session's own extensive ``pip-compile`` history (see the roadmap's found-after-the-fact log). Its
  most likely origin: a bare ``pip-compile requirements.in`` invocation at some point (no
  ``--output-file`` flag), which ``pip-compile`` defaults to writing as ``requirements.txt`` --
  never adopted into the documented workflow, never referenced by any install step, and not kept in
  sync since (the version drift between the two files' package sets confirms it stopped being
  regenerated). ``requirements-windows.txt`` (0 lines, tracked) is *not* the same kind of issue --
  README documents it correctly as a deliberate, empty placeholder (Windows installs PyTorch via a
  custom index URL instead, not via this file). Separately, ``tmp/need_review/dependencie_fix_win_linux.md``
  is an untracked scratch note proposing a different dependency-split design (separate
  ``requirements-linux.in``/``requirements-windows.in`` overlay files) that was never adopted --
  neither overlay file exists on disk; the design actually implemented (documented in README and
  CLAUDE.md SS11) compiles ``requirements-linux.txt`` directly from the shared ``requirements.in``
  on native Ubuntu instead. Flagged here as a real, disclosed finding, not silently cleaned up --
  removing a git-tracked file is the author's call, not a default "clean up whatever's found"
  action.
- **Speech Act Theory / Gricean Maxims classification -- explicitly deferred, not attempted.**
  Raised 2026-08-24 alongside ``hedge_ratio``/``booster_ratio`` (both shipped -- see
  :mod:`core.analysis.nlp_science`). Hedging/boosting are well-approximated by a lexicon ratio
  (Hyland 2005's own methodology); Speech Act classification (directive/commissive/expressive) and
  Gricean-maxim-violation detection are not -- a naive rule-based classifier for either would be a
  plausible-sounding but uncalibrated guess, risking exactly the kind of construct-validity failure
  this project has already caught twice this session (``semantic_overlap``, the benchmark
  leaderboard's ``mimicry_score`` -- see :doc:`04-llm-analytics`). Building either for real would
  need either a labeled dataset to validate a rule-based classifier against, or a second LLM call
  (functionally another cascade layer, with its own latency/scope tradeoffs CLAUDE.md SS6 reserves
  for the author). Neither is built; both are named honestly as unexplored, not silently skipped.
- **Interpretability stack (Integrated Gradients / Attention Rollout / Probing Tasks / Captum /
  TransformerLens) -- architecturally blocked by the current model-serving choice, not just
  unbuilt.** Raised 2026-08-24. This is not a "not gotten to it yet" gap the way the two items above
  are: all of these techniques need direct access to a model's gradients or internal activations,
  and ``OllamaClient`` only ever talks to Ollama's HTTP API (text and token counts in, text out --
  see :doc:`01-architecture`'s request-lifecycle trace). There is no gradient or activation tensor
  reachable through that interface at all, for any model Ollama serves. Achieving this would require
  a second, parallel model-loading path -- a real PyTorch/HuggingFace `transformers` model loaded
  directly in-process, bypassing Ollama entirely for whichever specific model is being interpreted
  -- which is a materially heavier compute/memory footprint than anything else in this project's
  pipeline, and directly conflicts with the "weak machine, no heavy new dependencies" constraint the
  author set for this same day's other additions. TransformerLens specifically also does not support
  the GGUF-format models Ollama serves at all, independent of the access-method question. Logged
  here as a named architectural fork for the author's own future consideration, not something a
  library addition would close.
