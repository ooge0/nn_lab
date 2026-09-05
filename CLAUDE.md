# CLAUDE.md — nn_lab (FastAPI rewrite)

Standing context for the AI coding agent. Read this before proposing or making changes. This file
describes the project as it **is** and the rules the work **must** follow — it is not a changelog.

---

## 0. What this project is

An **interpretable, statistically-validatable analyzer of LLM behavioral style.** It generates
synthetic text conditioned on behavioral archetypes, validates the generation, and runs a
linguistic + statistical analysis pipeline over the resulting corpus.

**Primary goal:** a portfolio artifact demonstrating LLM-QA / evaluation-testing competency for
hiring. It is **not** a product to sell. Every decision is judged against one question: *does this
demonstrate that I can test language models rigorously?* If an item does not serve that, it goes to
backlog, not into v1.

The differentiator being demonstrated is **measurement validity** — proving a metric measures what
it claims and that the signal is not noise — not breadth of features.

The author is a self-taught practitioner, working solo, with limited time and no code reviewer.
Optimize accordingly: correctness of the core over breadth of features.

## primary rules

# How to reduce token usage in Claude Code without losing effectiveness

The point isn't to make Claude do less — it's to stop it from pulling context it doesn't need for the current task. Main levers: CLAUDE.md, `.claudeignore`, path-specific rules, narrowly scoped skills, and delegating to a forked subagent with isolated context.

## 1. Explicit conditional rules in CLAUDE.md

The simplest and most effective thing — write conditional instructions in the format "if task X, don't do Y" instead of vague preferences:


### Context economy

- Design/styling/CSS task — don't read logs, don't run tests, don't look at backend code unless explicitly asked.
- Bug in a specific module — don't read the whole repo, scope to that module and its direct dependencies.
- If the app hasn't been run this session — don't open logs or check for runtime errors, they don't exist yet.
- Don't re-read a file already shown in this session if it hasn't changed since.
- Before editing a large file, use Grep/Glob to find the relevant section first, don't read the whole file.


This works because CLAUDE.md loads on every turn from the start, so these rules actually shape behavior from message one, instead of only when you remember to repeat them.

## 2. .claudeignore — never load what you never need

Extend what you already use for large projects:

```
node_modules/
dist/
build/
*.log
coverage/
.next/
__pycache__/
*.min.js
etc....
```
Anything Claude should never read in full is cheaper to exclude at the ignore level than to rely on it "just not going there."

## 3. Path-specific rules — targeted instructions per zone

Claude Code supports rules tied to paths (the same format nested skills use). Instead of one big "don't look at logs if it's a design task" instruction, tie behavior explicitly to a directory:

```
## frontend/**
Don't read backend/ or check DB migrations here unless explicitly requested.

## backend/**
Don't touch frontend/styles/ or run visual tests here.
```

This is literally the mechanism behind "don't check logs if it's a design task" — just formalized so Claude understands the boundary by task type on its own, without you repeating it every time.

## 4. Skills instead of repeated long prompts

If you keep asking for the same thing ("check migrations", "run lint and show the diff") — wrap it in a skill instead of typing it out each time. A skill only loads into context when actually invoked, unlike CLAUDE.md which is always present. That's a direct saving: a long instruction doesn't sit in context for the whole session if it's not needed right now.

```yaml
---
name: check-migrations
description: Check DB migrations for conflicts
disable-model-invocation: true
---
Check only files in migrations/, don't touch the rest of the code.
```

## 5. Forked subagent for "messy" work

For tasks like "read the whole codebase and find where X is used" — use `context: fork` with the `Explore` agent. This isn't just convenience, it's a direct token saving: the subagent works in a separate context, finds what's needed, and only a summary comes back into your main session, not every file it touched along the way.

```yaml
---
name: find-usage
description: Find all usages of a function/variable in the code
context: fork
agent: Explore
---
Find every place where $ARGUMENTS is used. Return a file list and a short summary, not the full code listing.
```

Without this, Claude greps/reads files in the main session itself, and all of that accumulates permanently in conversation history (until compaction). With a fork, only the result comes back.

## 6. Explicitly ask Claude not to re-read what hasn't changed

One common source of waste: Claude re-reading a file "just in case" before an edit. Rule for CLAUDE.md:
```
Don't re-read a file if it was already shown in this session and hasn't been edited since.
```

## 7. Watch the size of CLAUDE.md and the skill list itself

Paradox: if too many context-economy rules pile up, the list itself starts costing tokens (the skill listing weighs roughly 1% of the model's context window). Keep CLAUDE.md compact, move long reference material into separate files that CLAUDE.md just points to — they only load if actually needed.

## Base template — drop into CLAUDE.md right now

```
## Context economy rules

1. Don't read logs or check runtime state if the app hasn't been run in this session.
2. Design/styling task — don't touch backend, DB, or tests unless explicitly asked.
3. Before editing a large file — Grep/Glob first, then read only the relevant section.
4. Don't re-read a file if it hasn't changed since it was last shown.
5. For repo-wide search, use a forked Explore agent instead of reading files one by one in the main session.
```

## Senior-dev rules — the stuff people learn the hard way

Not gimmicks, not micro-optimizations — habits from people who actually understand how not to overload a language model with context it doesn't need.

6. Never ask Claude to "read the whole project to understand it" as a first step. State the actual entry points (main file, router, schema) up front — orientation-by-full-read is the single biggest silent token sink.
7. Keep CLAUDE.md to facts and standing constraints only. If a paragraph explains *why* a rule exists, that belongs in a comment or doc, not in the file that loads on every single turn.
8. One task, one topic per message. Don't bundle "also check the auth flow while you're at it" into an unrelated bugfix — mixed intent forces broader context loading than either task needs alone.
9. Prefer diffs over full-file pastes when describing what changed. Full-file context is only worth it the first time Claude touches a file; after that, diffs carry the same information for a fraction of the tokens.
10. Don't paste stack traces you haven't looked at yourself. A raw 200-line trace where the actual error is in the first 5 lines burns tokens for no signal — trim it before pasting, or point Claude at the file/line directly.
11. Split "explore" and "implement" into separate turns, not one. Asking Claude to investigate and fix in one shot means every exploratory read stays in context for the fix too, even the dead ends.
12. Close the loop on a subtask before opening a new one. Long-running sessions that jump between five half-finished tasks force Claude to keep all five in working memory instead of one at a time.
13. Don't ask for speculative work ("also make it configurable in case we need X later") unless X is a real, near-term requirement. Every hypothetical branch Claude writes and reasons about is context spent on a feature that may never exist.
14. Trust the model's default read granularity. The senior instinct to say "just read the whole module to be safe" is usually wrong here — scoped reads plus targeted follow-up reads are cheaper than a defensive full read, and just as correct.
15. When a task is genuinely exploratory and you don't know the entry point yourself, say so explicitly and let Claude use Explore/fork — don't make Claude guess by dumping the whole repo tree into the prompt "just in case."
16. Periodically prune completed threads from long sessions. A session that has accumulated ten finished tasks' worth of history is paying a compaction/re-attachment tax on all of it going forward — start a fresh session per unrelated task rather than one marathon thread.

---

## 1. Hard scope boundaries

**In scope for v1 (the moat — must be rigorous and tested):**
- Structured judge (not `if "YES" in response`) → returns `{verdict, confidence, rationale}`.
- Malformed-output classification: `VALID / MALFORMED_JSON / TRUNCATED / EMPTY / SCHEMA_ERROR / API_ERROR / FORMAT_ERROR`.
- Per-response evaluation cascade (see §3).
- Corpus-level confirmatory validation (Silhouette / Davies-Bouldin / label-alignment ARI as construct-validity proxies) — a **separate stage** from the cascade (see §3).
- Interpretable linguistic metrics (TTR, ARI, coherence, modality, self-focus, etc.).

**Out of scope for v1 (backlog — do NOT start or extend these without explicit approval):**
- Neo4j / knowledge graph. NOTE: legacy Neo4j code already exists in the tree
  (`core/service/neo4j_service.py`, `core/tabs/knowledge_graph.py`,
  `utils/other/neo4j_services.py`, `results/knowledge_graph_analyses/`). As of Stage 16 it is
  reached via `run_knowledge_graph.py` (a small standalone Streamlit script extracted from the
  original monolith, itself now archived at `legacy/streamlit_app.py`) rather than being removed —
  the author decided to keep it running standalone, not sunset it. Do not build on it or extend it
  further. See §5.
  **"Untouched" scope, precisely defined:** no refactoring, no re-layering behind a `core.domain`
  interface, no logic/behavior changes, no import-path moves — none of that applies to this
  subsystem, ever, without a separate explicit decision. The one standing, narrow exception is
  **docstring/comment clarifications that add historical or architectural context without changing
  behavior** — e.g. `core/tabs/knowledge_graph.py`'s class docstring gained an "Implementation
  status" note (2026-08-22) explaining *why* it still says "Streamlit tab" and pointing at
  `run_knowledge_graph.py`, precisely so a future reader doesn't mistake settled, deliberate scope
  for an oversight. If a change would alter what the code *does* — not just what it *says* — the
  "do not build on it or extend it" rule above still applies without exception.

  **Second standing exception, 2026-09-05, explicit and narrow (same precedent as SS4/SS6's judge
  fix):** a resume-claims audit found a real, author-disclosed bug — 3 of 4 PageRank scripts in
  `KnowledgeGraph.knowledge_graph_tab` failed with `Procedure.ProcedureNotFound` against this
  project's own documented Neo4j setup (the GDS plugin was installed but never unrestricted/
  allowlisted in `neo4j.conf` — a config gap, not a missing dependency) — plus zero test coverage.
  Author asked for a real, working fix with technical proof, not just a diagnosis. Fixed: the
  `neo4j.conf` procedure-security config (outside this repo, on the local Neo4j install — not a
  code change), and one real code bug in `core/tabs/knowledge_graph.py` (script-4 called
  `gds.pageRank.stream` with no exists-check/projection guard, unlike scripts 1/3 — now matches
  their pattern). Added `tests/unit/test_knowledge_graph.py` (4 tests, mocked `py2neo.Graph`, no
  live server — this project has no Docker/disposable-test-database story, so this checks
  query-construction/ordering, not that a real Neo4j+GDS deployment works). Real end-to-end proof
  captured by driving the actual `run_knowledge_graph.py` Streamlit app via Playwright against real
  run data (sync + all 4 PageRank scripts, screenshots + real PageRank output saved) — see
  `docs/source/wiki/07-knowledge-graph-results.rst` for the full record, root cause, and honest
  limitations (GDS's graph catalog doesn't survive a Neo4j restart; tabs 5/6 never touch Neo4j at
  all — pure pandas/scipy on the in-memory DataFrame). Explicitly **not** done: no refactor, no
  move behind a `core.domain` interface, no promotion into the rewrite's own testing/architecture
  discipline — the subsystem now demonstrably works and has some real coverage, but stays exactly
  where CLAUDE.md SS1 already puts it.

  **Same exception, extended same day:** a follow-up request asked for the most useful real
  scenario for this subsystem, grounded in real data-lineage/AIOps root-cause practice (researched,
  not invented — see the wiki page's sources). Added a second, additive sync building a
  failure-mode/cascade-lineage graph (`Response` → which `Layer0`/`Layer1`/`Layer2`/`Judge` outcome
  it actually reached, `Model`/`Archetype`/`Bias`/`Run` context, RAG-chunk provenance recovered from
  the persisted `rag_context` string) plus 3 real root-cause Cypher queries, exposed as a new
  "Root Cause (Failure-Mode Graph)" tab — does not touch or replace the original Archetype/Bias/
  PageRank graph. Two real things found and fixed before this shipped, not assumed correct: a
  classic Neo4j `MERGE`-on-anonymous-node pitfall that silently duplicated `CascadeStage` reference
  nodes (caught by a synthetic smoke test against the live database before writing it into the app),
  and a real pipeline-semantics subtlety (Layer 2's hallucination check runs unconditionally on echo
  status, so an echo-rejected response can still show `layer2_checked=True` — `reached_judge` is
  computed explicitly as `layer0==VALID and not echo`, never inferred from "reached a later stage").
  7 new tests (11 total for this module). Real proof captured the same way as the PageRank fix —
  driving the actual Streamlit app via Playwright against a real 500-response, RAG-enabled run —
  with genuinely actionable findings (e.g. one student model echoing its own bias instruction back
  more than 2x as often as another; one RAG knowledge category linked to 36 of the run's echo
  failures). Full record: `docs/source/wiki/07-knowledge-graph-results.rst`. Same explicit
  boundaries as before: no refactor into `core.domain`, no promotion into the rewrite's own
  architecture/testing discipline.

  **Fourth entry, 2026-09-05, a real reversal this time, not another narrow exception:** the
  author explicitly decided to promote the failure-mode/cascade-lineage graph specifically (not
  the original Archetype/Bias co-occurrence graph, not the PageRank scripts, not Hypothesis
  Testing/Uncertainty Analysis) out of this quarantine and into the layered architecture, full
  depth (a real `core.domain` interface + adapter, matching `LLMClient`/`Judge`/`Repository`/
  `KnowledgeBase`), explicitly to leave room to grow toward the graph-representation-learning
  roadmap (`docs/source/wiki/08-graph-representation-learning.rst`) without a later redesign.
  Shipped: `core.domain.interfaces.GraphRepository` (4 methods: `sync_failure_mode_graph`,
  `echo_rejections_by_model`, `terminal_stage_by_archetype`, `rag_chunks_linked_to_echo`),
  `core.adapters.neo4j_repo.Neo4jGraphRepo` (Cypher ported verbatim from the Streamlit version,
  not redesigned — reads its own `[neo4j]` config directly rather than importing the untouched
  `Neo4jService`, keeping the new layer independent of the legacy one its one covered capability
  was promoted out of), `api/routers/knowledge_graph.py` + `web/templates/knowledge_graph.html`
  (a real `/knowledge_graph` page, linked from `_nav.html` under `[corpus]`). The corresponding
  code was then **removed** from `core/tabs/knowledge_graph.py` (the "Root Cause (Failure-Mode
  Graph)" tab it briefly carried) — verified live parity first (identical real numbers — 27 vs. 12
  echo-rejections by model, 36 echo-rejections linked to the `paranoid`/`Behavior` RAG category —
  through the new FastAPI page against the same live Neo4j data) before deleting the Streamlit
  duplicate, matching the Stage-16 precedent for every other tab this project has ever retired.
  20 tests (11 unit for the adapter, 9 integration for the router — no live server needed, mocked
  `py2neo.Graph`). What's still on the Streamlit script (`run_knowledge_graph.py`) and still fully
  under the original quarantine, unchanged: the plain Archetype/Bias co-occurrence sync, all 4
  PageRank scripts, Hypothesis Testing, Uncertainty Analysis.

  **Same day, later: Stages 4 and 5 of the roadmap shipped into `GraphRepository`/`Neo4jGraphRepo`.**
  `behavioral_communities()` — Leiden community detection over Archetype/Bias/Model/CascadeOutcome
  (connected via a materialized `CO_OCCURS_WITH` co-occurrence edge, since they're never directly
  connected otherwise); `structural_similarity()` — `gds.fastRP.mutate` + `gds.knn.stream` for
  analogy/anomaly over the same graph, which independently agreed with Leiden's own communities on
  real synced data. Two new buttons on `/knowledge_graph`, both reporting GDS's own real numbers
  (modularity; similarity scores) as validation, not eyeballed results. 10 new tests total (23
  unit, 13 integration). Full detail, a real `gds.nodeSimilarity`/`gds.knn` correction found while
  implementing, and what's still open (Stage 6, the NMI cross-check against UMAP/HDBSCAN):
  `docs/source/wiki/08-graph-representation-learning.rst`.
- Authentication.
- Hosted inference migration (stay on local Ollama for now).
- Any product/marketing/"client-facing metrics" layer.

---

## 2. Target architecture

Layered, dependency direction strictly inward. Core must not import any web framework.

**Status: built.** As of Stage 16, this layout exists and is the primary way to run the app — see
§12 for what's actually on disk today. This section is kept as the standing architectural rule, not
just a historical target.

```
core/
  domain/      # entities + interfaces (Protocols/ABCs), ZERO framework imports
  services/    # ExperimentRunner, MetricsEngine — orchestration, emits events, no I/O rendering
  adapters/    # OllamaClient, JSONLStore, SQLiteRepo (impls of domain interfaces)
api/           # FastAPI routers, pydantic DTOs, SSE endpoints
web/           # Jinja2 templates + HTMX
cli/           # config-driven batch runner
tests/         # see §6
docs/          # Sphinx + myst-parser (source only; build output is gitignored)
```

`core/service/`, `core/tabs/`, and the legacy Streamlit scripts (`legacy/streamlit_app.py`,
`streamlit_app_lang_localization.py`) are the only pieces still outside this layout — the Neo4j
subsystem, kept deliberately untouched per §1, and `streamlit_app_.py`/
`streamlit_app_lang_localization.py`, both still under author investigation (see §5). Everything
else (`core/analysis`, the old `core/rag/`) has already been migrated in.

Rule: `web`/`api` → `services` → `domain`. `adapters` implement `domain` interfaces; `domain`
knows nothing about them.

**Interfaces to define first, before implementations:**
`LLMClient`, `Judge`, `PromptStrategy`, `Repository`.
Wire existing naive logic behind these interfaces first (keep `KeywordJudge` as-is initially so
nothing breaks), then evolve.

**Delivery stack:** FastAPI + Jinja2 + HTMX. SSE for live run progress (replaces Streamlit rerun).
SQLite + SQLAlchemy for run metadata, JSONL on disk for artifacts. Backend implementation is the
focus; the frontend is thin and may be rough.

**Deployment target:** bare-metal Windows and Ubuntu. **No Docker, no cloud.** Keep the run/serve
story to a plain `uvicorn` invocation and a documented venv setup that works on both OSes. Do not
introduce container-only or cloud-only assumptions.

**⚠️ Known, disclosed gap (2026-08-24, not yet fixed):** the Ubuntu half of this has not actually
been verified since the FastAPI rewrite began — every stage's manual "run it and check" step in the
plan's found-after-the-fact log was performed on Windows. `requirements-linux.txt` is stale
(last regenerated 2026-06-22, predating `fastapi`/`sqlalchemy` being added to `requirements.in`) —
confirmed neither package appears in it today. The author's explicit call, when this was raised: keep
it as a documented gap rather than have the AI agent provision a WSL Ubuntu distro to verify it in this
session. See `docs/source/wiki/02-tools-and-stack.rst`'s disclosed-gaps section for the full finding
and the exact fix (`pip-compile requirements.in --output-file=requirements-linux.txt`, must run on
real Ubuntu). Until that's done and a real Ubuntu run is confirmed, treat "works on both OSes" as
aspirational for the current dependency lock files, not a verified fact.

---

## 3. Two separate evaluation stages — do NOT collapse into one flow

This is a settled design decision. There are **two distinct pipelines** that operate at different
granularities. Merging them into a single linear flow is a known error and must not be done.

### 3a. Per-response cascade (runs on EACH response)

Fail-fast, cheapest deterministic checks first, generative judge last and only for what the lower
layers cannot resolve. Local, linear, unit-testable one example at a time.

```
response + context
 → Layer 0: deterministic gates    (regex, format, schema, length)   fail → stop
 → Layer 1: STS embeddings         (topical/semantic proximity)
 → Layer 2: specialized classifiers (NLI for factual contradiction; sentiment; toxicity)
 → Layer 3: generative judge       (only for open-ended intent/appropriateness)
 → aggregate → verdict + score
```

**Routing is static/deterministic (rule-based cascade), NOT an LLM orchestrator.** The whole point
of this project is reproducible, explainable evaluation; an LLM deciding which tool to call
reintroduces the black box one level up. Routing must be as reproducible as the tools it routes.

### 3b. Corpus-level confirmatory analysis (runs on the ACCUMULATED corpus, after many responses)

Global and statistical. Only meaningful over many responses; cannot run on a single one.

```
accumulated corpus of scored responses
 → linguistic / NLP metric matrix per response
 → dimensionality reduction (UMAP)      [needed: raw features collapse into one cluster otherwise]
 → clustering (HDBSCAN)
 → cluster-validity metrics (Silhouette, Davies-Bouldin, label-alignment ARI)
 → data visualization
 → benchmark / construct-validity report
```

**Why separate:** clustering needs the whole set to form clusters, so it cannot sit on the path
that decides a *single* response. The per-response "decision" (§3a) belongs at the end of the
cascade; clustering → viz → benchmark (§3b) is a downstream stage over the whole dataset. The
earlier planning note that listed `response → linguistic → NLP → clustering → viz → decision →
score` as one flow was wrong precisely because it put a corpus-level step inside the per-response
path. Keep them as two stages.

---

## 4. Known core defect to fix (highest priority) — **Resolved for Layer 3, see below**

The legacy validator decides pass/fail via string-matching "YES" in the judge's raw output. This is
the single most load-bearing and most fragile mechanism — every downstream metric inherits its
unreliability. Replacing it with a structured judge is the top correctness task. Self-critic mode
(same model generates and judges) has a known sycophancy risk; at minimum, log self-critic vs.
cross-model pass-rate deltas so the inflation is measurable.

**First concrete milestone:** a `Judge` that takes one response and returns
`{verdict, confidence, rationale}`, with three unit tests — a clear pass, a clear fail, and a
malformed input. This single deliverable teaches the interface pattern, structured output, and
testing-the-seam at once, and it is the exact thing the project's moat depends on.

**Resolved (2026-08-24), by the author's explicit decision, not a default AI-agent
"improve whatever's found" change:** §6's "author writes the judge by hand" boundary was
deliberately, narrowly lifted for this one fix, after an explicit discussion of scope (see
`docs/source/wiki/04-llm-analytics.rst` and this plan's own found-after-the-fact log for the full
record). What actually shipped, scoped tightly to what the author asked for — comfortable on a
weak machine, no paid subscriptions, minimal complexity, not the full cascade:

- **Layer 3 (the judge itself):** `NaiveJudge` deleted, replaced by
  `core/adapters/structured_judge.py`'s `StructuredJudge` — genuinely parses the JSON it requests
  (`json.loads`, not `"true" in text`), populates `confidence`/`rationale` for real, and falls back
  to a *distinguishable* `verdict=False, confidence=0.0` (not an indistinguishable-from-a-real-"no"
  one) on a malformed response.
- **Layer 0 (deterministic gates):** `core/analysis/response_classification.py`'s
  `classify_response` — `VALID`/`EMPTY`/`MALFORMED_JSON`/`TRUNCATED`/`SCHEMA_ERROR`, run before
  metrics computation; a non-`VALID` response skips metrics computation *and* the judge call
  entirely (`ExperimentRunner._run_one`).
- **Layer 1 (a narrow, real-data-calibrated slice, not the full topical-STS gate SS3a
  describes):** `is_echo_response` in the same module — an echo detector, not a general topical-
  relevance gate. Calibrated against real generated data, not guessed, and the calibration itself
  is a genuine "measurement validity" finding worth keeping: the first design attempt assumed the
  standard STS intuition (low similarity to the prompt = off-topic = reject); real data showed this
  was backwards for this task specifically — genuine responses scored 0.06-0.30 similarity to their
  own bias text, confirmed echo failures (SS0's real-data finding, 7/125 cases) scored 0.59-0.98,
  because this project's `bias` field is a short, comma-separated style/tone *tag list*
  (`"personalization, formal, toxic"`), not a natural-language question a good response should
  closely paraphrase. The threshold rejects *high* similarity, not low, for this reason — see the
  module's own comment for the full cause-and-effect account. **Whether other properties of the
  `bias` field's content (register, valence, lexical rarity, or other neurolinguistic dimensions
  the archetype-conditioning design leans on) deserve their own validation is an explicitly open
  question, not resolved here** — flagged for the author's own future exploration, named honestly
  as unexplored territory rather than guessed at.
- **Layer 2 — partially built 2026-08-24, logging-only, still not a gate.**
  `core/analysis/hallucination_check.py`'s `check_hallucination` is a real local NLI
  cross-encoder (`cross-encoder/nli-MiniLM2-L6-H768`, same MiniLM family/weak-machine constraint as
  the embedder) checking a response against RAG-retrieved context for factual contradiction — but
  **only when RAG is enabled** (no ground-truth document exists to check against otherwise), and
  **deliberately non-gating**: it persists a real predicted label + contradiction score but does not
  reject responses or touch `v_ok`. Unlike Layers 0/1, no real-data calibration exists yet for a
  rejection threshold — shipping an uncalibrated gate would repeat exactly the mistake Layer 1's own
  calibration process caught (see the threshold-inversion finding above), just for a different
  field. Turning this into a real gate is still the author's own future work, pending a review of
  real RAG-enabled run data. Sentiment/toxicity classifiers (the other half of CLAUDE.md §3a's
  original Layer 2 description) remain entirely unbuilt.

---

## 5. Known cleanup items (real duplications / scope creep in the current tree)

These are actual issues visible in the current file structure. Surface them; do not silently
"improve" around them.

- ~~`core/analysis/data_contract.py` AND `core/analysis/data_contract_old.py` coexist.`~~ **Resolved:**
  the two were functionally identical (`_old.py` lacked only docstrings and had one unused validator
  param); `data_contract.py` is the one every caller imports, `_old.py` had zero importers and has
  been deleted.
- **`core/service/neo4j_service.py` AND `utils/other/neo4j_services.py` are NOT duplicates** —
  despite the similar names, they do unrelated jobs and both are live: `neo4j_service.py` is a
  `Neo4jService` class (py2neo client wrapper — load credentials, connect, health-check), used by
  `run_knowledge_graph.py` (and, historically, `legacy/streamlit_app.py`) and
  `core/tabs/knowledge_graph.py`; `neo4j_services.py` is free functions (`start_neo4j`,
  `neo4j_running`, `find_neo4j_bin`) that launch the Neo4j server *process* via subprocess, used
  only by `run_knowledge_graph.py`. Do not delete either on the assumption they're redundant —
  one's a client, the other's a process launcher.
- ~~**Neo4j subsystem present despite being out of scope for v1**~~ **Resolved (Stage 16):** the
  author chose to keep it running standalone rather than remove it — `tab_knowledge_graph` was
  extracted from the original monolith into its own small script, `run_knowledge_graph.py`, reusing
  `JSONLStore` to read whichever run the FastAPI app or CLI generated. The Neo4j subsystem itself
  (`neo4j_service.py`/`neo4j_services.py`/`knowledge_graph.py`) remains untouched, per §1.
- **`knowledge/rag/` still uses raw clinical terms** (`epileptoid.txt`, `hysteroid.txt`,
  `paranoid.txt`, `schizoid.txt`). This contradicts the deliberate "behavioral archetype"
  relabeling (de-risking) decision — the soft naming has not reached the data files.
- ~~**`failure_taxonomy` appears in the docs build but may have no source module.**~~ **Resolved:**
  `core/tabs/failure_taxonomy.py` no longer exists on disk (deletion already staged in git); the
  canonical Sphinx build (`docs/source/_build/`) has zero references to it. A reference does still
  linger in the stale, superseded `docs/build/` directory (gitignored, not the canonical output
  location per §12) — harmless, not shipped anywhere.
- **The same `lab_export_*.jsonl` files appear under both `results/` and `test_data/`.**
  Investigated at Stage 16: `test_data/`'s 12 JSONL files are confirmed **not referenced by any
  test or code anywhere in the repo** (full-repo grep, zero hits) — despite the directory's name,
  nothing treats it as a fixture source; `results/lab_experiment_results/` (read via `JSONLStore`)
  is the only tree the app actually uses. Two files are byte-identical duplicates between the two
  trees. Author's explicit decision: leave both trees exactly as they are, no cleanup action taken
  — this is a known, accepted state, not an open question.
- **`streamlit_app_.py`'s characterization above was wrong, corrected at Stage 16.** It is not "an
  undifferentiated duplicate of `streamlit_app.py`" — a real diff shows 3013 changed lines,
  opposite Neo4j wiring, and an import of `core.tabs.failure_taxonomy` (a module that no longer
  exists, so the file cannot currently run). It is also untracked in git (`git ls-files` shows
  nothing), unlike every other `streamlit_app*.py` variant. Flagged to the author at Stage 16, who
  chose to investigate further before deciding its fate rather than deleting or archiving it —
  it remains untouched, at the repo root, not yet triaged.
- **`streamlit_app_lang_localization.py`** — confirmed still a genuinely distinct, git-tracked,
  actively-maintained localized variant (its RAG import was deliberately updated during the Stage 3
  `core/rag/` → `core/adapters/rag/` move, alongside `streamlit_app.py`, so it hasn't been
  abandoned). 2566 lines different from `streamlit_app.py`. Author deferred a decision on its fate
  at Stage 16; still untouched.

---

## 6. Working discipline (staging)

Guards against the author's documented failure mode: accumulating conceptual scope faster than
working implementation, and infinite improvement loops without a solid core.

- **One front at a time.** Exactly one component open. The next does not start until the current
  one has tests and is closed. No "big bang" rewrites.
- **Stage gates.** Build in stages (0 → N). At the end of each stage, **stop and get explicit
  approval** on priorities for the next stage. Do not auto-proceed across stage boundaries. The
  file cannot enforce this — the author must actually stop at each boundary.
- **Author writes the moat.** The AI agent handles mechanical layer-shuffling, boilerplate removal,
  porting, and scaffolding, shown as diffs. The author writes the judge, the cascade logic, and the
  confirmatory layer by hand (agent reviews, does not author these) — they are the
  interview-defensible core. **One explicit, narrow exception, made 2026-08-24 (see §4):** the
  author asked the AI agent to fix `NaiveJudge`'s parsing bug directly (real JSON parsing,
  `confidence`/`rationale` population) plus a scoped Layer 0 (deterministic gates) and a narrow
  Layer 1 (echo detection only, not the full topical-STS gate) — explicitly *not* the judge's own
  pass/fail criteria (still the model's own prompt-driven judgment, not hand-tuned rules) and
  explicitly *not* Layer 2. This is a recorded, one-time author decision to lift the boundary for a
  specific, discussed scope — not a standing change to this rule for future work.
- **Spec follows code.** No new design/spec note for a component that has no working implementation.
  Existing Obsidian notes are frozen reference; convert them to code/tests or archive them.
- **Prefer the smallest change that closes a defect.** Breadth is the known risk, not the goal.

---

## 7. Testing (this IS the portfolio signal — treat as first-class)

Because the project demonstrates *testing* competence, tests are not an afterthought; they are the
product.

- **Unit tests for business logic AND for borrowed math/NLP/linguistic methods.** Do not assume a
  metric from a third-party package is correct for our use — pin expected outputs on known inputs
  (e.g. TTR / ARI / cosine coherence on fixed strings) so a dependency change surfaces as a failing
  test. Where feasible, prefer validated libraries (`textdescriptives`, `lexicalrichness`) over
  hand-rolled metric code, and test the seam.
- **Layers:** unit, functional, API, and Playwright E2E (Chrome + Firefox, headless) with a
  lightweight Page Object Model.
- **Reporting:** Allure. Docstrings on all core + test files so Allure shows real descriptions, not
  bare names.
- **Logging:** loguru across the app.
- **tox:** environments for lint / py / typecheck / docs / e2e-chrome / e2e-firefox.
- **Static quality:** black across the codebase; fix real mypy findings rather than suppressing
  them.

---

## 8. Documentation

- **README** structured as: Core app → Services → Architecture → Tests → API Reference.
- **Sphinx** docs, with the README included as a page via **myst-parser**.
- **Architecture page:** live-regenerated ER diagram, business-flow diagram, class-relations
  diagram.
- **Tests reference page** + **API reference** (autodoc from docstrings).
- Keep docs regenerable — diagrams are generated from the code, not hand-drawn and left to rot.
- The methodology README (how the testing approach works, not a feature list) is the single most
  valuable interview artifact — keep it honest and current.

---

## 9. Reusable skill

A personal AI-agent skill, `webapp-refactor-plan`, distills this project's planning methodology
(analyze legacy → staged build order → per-stage approval gates → tests-before-next-stage) for
reuse on future projects. Keep it generic — it should not carry this project's domain specifics.

---

## 10. How to work with the author

- Give substantive critique, not praise. The author explicitly wants to be told when something is
  wrong, and values reviewers who engage with the internals over people who approve.
- When a supplied instruction conflicts with §1–§3 (scope, architecture, the two-stage separation),
  **flag it and ask** — do not silently reconcile or "improve."
- The author is learning the fundamentals alongside the build. When introducing a concept (NLI,
  STS, cluster validity), explain it plainly enough to code against, not just name it.

---

## 11. Commands

**Environment setup:**
```bash
# Windows 11 (Python 3.12 — required for the current PyTorch/CUDA stack)
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --no-cache-dir
pip install -r requirements-base.txt

# Ubuntu
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-base.txt -r requirements-linux.txt
```

**Run the app** (three front ends, see §12 — the first two share one `ExperimentRunner`):
```bash
uvicorn api.app:app --reload                          # FastAPI web app — primary
python -m cli.run_experiment --config cli/example_config.toml   # headless batch runner
streamlit run run_knowledge_graph.py                   # Neo4j knowledge-graph explorer only
```
`legacy/streamlit_app.py` (the pre-rewrite monolith) is still on disk and still technically
runnable, but is reference-only as of Stage 16 — every tab it has besides `tab_knowledge_graph` now
has a tested FastAPI/CLI equivalent.

**Operational console** (`cli/manage.py`, added 2026-08-25 — distinct from `cli/run_experiment.py`
above, which runs one experiment; this is day-to-day ops without the web UI up):
```bash
python -m cli.manage serve [--host H] [--port P] [--no-reload]   # same as the uvicorn line above
python -m cli.manage status                                       # Ollama/NLTK/spaCy reachability
python -m cli.manage list-runs                                    # every run JSONLStore knows about
python -m cli.manage export-db <run_id> [--db-path P] [--overwrite]   # copy one run's JSONL into SQLite
```

**Tests** (run from repo root; `tests/conftest.py` inserts repo root onto `sys.path`, provides a
session-scoped `rag` fixture built from `knowledge/rag/`, and applies to every subfolder below by
pytest's normal conftest-cascade — it is not duplicated per folder):
```
tests/
  unit/          # pure logic against fakes/mocks — no TestClient, no browser
  integration/   # functional/API tests via FastAPI TestClient + fake adapters
  legacy_rag/    # pre-rewrite RAG suite against the real embeddings/FAISS engine
  e2e/           # Playwright, real browser — MUST run in its own process, see below
```
```bash
pytest tests --ignore=tests/e2e -v   # unit + integration + legacy_rag
pytest tests/e2e -v                  # Playwright E2E, separately (needs `playwright install chromium` once)
tox -e py312     # same as the first command, plus writes results/pytest_test_results/pytest_report.html
tox -e e2e       # same as the second command, in its own tox env
tox              # runs the platform-matched env (win32 or linux) from tox.ini's envlist — does not include e2e
```
**Why `tests/e2e` must run in a separate process, not just a separate folder:** `pytest-playwright`'s
sync driver leaves the main-thread asyncio event loop unusable for any later code that calls
`asyncio.run()` directly (e.g. `core/services/_sse.py`'s bridge tests) — confirmed empirically: running
`tests/e2e` before `tests/unit` in one `pytest` invocation makes 20 unrelated unit tests fail with
`RuntimeError: asyncio.run() cannot be called from a running event loop`, while either suite run alone
is green. This is a real interaction bug in the Playwright/asyncio pairing, not something a fixture in
this repo can clean up — hence the hard split into two invocations/tox envs instead of relying on file
ordering (which is what silently avoided this before `tests/` had subfolders).

Run a single test: `pytest tests/legacy_rag/test_contract.py::test_name -v` (path reflects the file's
category folder — see the tree above).

**Dependency changes:** edit `requirements.in` only, then recompile — never hand-edit the
generated `requirements-*.txt` files:
```bash
pip-compile requirements.in --output-file=requirements-base.txt
pip-compile requirements.in --output-file=requirements-linux.txt   # must run on Ubuntu
```

**Resolved (2026-08-24):** `pyproject.toml` now holds `[tool.black]`/`[tool.ruff]`/`[tool.mypy]`
config, and `tox -e lint` runs `ruff check .` + `mypy core api cli web utils` (matching pinned
`requirements-dev.in` versions exactly: `ruff==0.15.17`, `mypy==2.1.0` — installing a bare, unpinned
`ruff`/`mypy` into an isolated tox env was tried first and pulled a newer `ruff` with a different
default rule set, a live demonstration of why this project pins tool versions everywhere else too).
All three tools' scope deliberately excludes the untouched Neo4j subsystem (§1) and the
legacy/undecided `streamlit_app*` variants (§5/§12) — the same paths `.coveragerc` already omits
from coverage measurement, kept consistent across all four tools rather than each inventing its own
scope. `black .` was run once across every in-scope file (86 of 119 live-code files had never been
formatted before; 52 remained after the legacy/Neo4j exclusion) — a genuine repo-wide reformat,
confirmed via the full regression suite before and after. Adding `pyproject.toml` had one real,
non-obvious side effect worth remembering: `tox.ini`'s `isolated_build = true` started trying to
build this project as an installable wheel for *every* env once a `pyproject.toml` existed, and
setuptools' auto-discovery failed outright on this repo's flat, 12-top-level-directory layout
("Multiple top-level packages discovered"). Fixed by adding `skip_install = true` to `[testenv]` —
this project was never meant to be pip-installed as a library (tests reach it via
`tests/conftest.py`'s `sys.path` insert), so skipping the build entirely is correct, not a
workaround. `black` itself is **not** run by `tox -e lint` — CI-style gating on formatting is a
separate decision from having the tool configured and runnable, not made here.

---

## 12. Current codebase map (post-Stage-16)

The target layout in §2 is now built and is the primary way to run the app (Stages 0-15 complete;
Stage 16 did cutover/cleanup). What's actually on disk today:

**Primary (FastAPI rewrite):**
- **`api/`** — FastAPI app (`app.py`) + routers (`experiments`, `runs`, `analytics`, `nlp`,
  `clusters`, `model_evo`, `benchmark`, `monitor`, `faq`, `demo`, `db_export`, `api_status`,
  `knowledge_graph`). `api/_paths.py` centralizes absolute `TEMPLATES_DIR`/`STATIC_DIR`/`REPO_ROOT`.
- **`web/`** — Jinja2 templates + HTMX (`web/templates/`), Plotly/matplotlib chart-building
  (`web/plotting/`, one module per tab), vendored `htmx`/`plotly.min.js` (`web/static/vendor/`, no
  CDN dependency).
- **`cli/`** — `run_experiment.py` (Stage 15's config-driven batch runner) + `example_config.toml`.
- **`core/domain/`** — `entities.py` (pydantic models incl. `ExperimentConfig`, `RunRecord`,
  `GenerationResult`, `JudgeVerdict`) + `interfaces.py` (`LLMClient`, `Judge`, `PromptStrategy`,
  `Repository`, `KnowledgeBase`, `GraphRepository` — the last added 2026-09-05, see §1). Zero
  framework imports.
- **`core/services/`** — `ExperimentRunner` (orchestration), `MetricsEngine` (Stage 7),
  `cluster_discovery.py` (Stage 10's `run_plain_hdbscan`/`run_behavioral_topology`/
  `compute_fit_indices`), `_sse.py` (the asyncio-queue bridge shared by the web app and reused
  internally by the CLI's own `asyncio.run()` wrapper).
- **`core/adapters/`** — `OllamaClient` (native `/api/chat`, real token/timing telemetry),
  `JSONLStore`/`SQLiteRepo` (both implement `Repository`), `StructuredJudge` (CLAUDE.md §4),
  `NaivePromptStrategy`, `rag/` (moved here from `core/rag/` in Stage 3:
  `chunking.py`, `ingestion.py`/`RAGEngine`, `retriever.py`, `vector_store.py`, `knowledge_base.py`),
  `neo4j_repo.py`/`Neo4jGraphRepo` (implements `GraphRepository`, added 2026-09-05 — the failure-mode
  graph, promoted out of the legacy Neo4j subsystem, plus `behavioral_communities()`/Leiden and
  `structural_similarity()`/node-similarity added the same day; see §1's fourth Neo4j entry).
- **`core/analysis/`** — the linguistic/statistical metric implementations
  (`calculate_advanced_linguistic_metrics.py`, `nlp_science.py`, `neuro_metrics.py`,
  `model_evaluation.py`, `data_contract.py`) plus `cluster_discovery.py` (the pre-existing
  `ClusterDiscovery` KMeans+PCA class, business logic only — presentation moved to
  `web/plotting/cluster_charts.py`). This is where §1's in-scope "moat" metrics live, already wired
  behind `domain` interfaces via `core/services/experiment_runner.py`.

**Legacy (untouched, or reference-only — see §1/§5):**
- **`core/service/neo4j_service.py`** and **`utils/other/neo4j_services.py`** — the Neo4j client
  and process-launcher, untouched per §1, now used by `run_knowledge_graph.py`.
- **`core/tabs/knowledge_graph.py`** — Streamlit tab rendering for the (out-of-scope) knowledge
  graph: the plain Archetype/Bias co-occurrence sync, all 4 PageRank scripts, Hypothesis Testing,
  Uncertainty Analysis. Untouched, per §1 — the failure-mode graph this file briefly also carried
  was promoted out to `core/adapters/neo4j_repo.py`/`api/routers/knowledge_graph.py` 2026-09-05
  (see §1's fourth Neo4j entry) and removed from here once real parity was verified.
- **`run_knowledge_graph.py`** (repo root) — Stage 16's small standalone script: loads a run via
  `JSONLStore`, calls `KnowledgeGraph.knowledge_graph_tab(df)`. The only live Streamlit entry point,
  now covering only what's still listed above (the failure-mode graph is reachable at the FastAPI
  app's `/knowledge_graph` page instead).
- **`legacy/streamlit_app.py`** — the original ~3,400-line monolith, moved here at Stage 16
  (`git mv`, history preserved). Reference-only; every tab besides `tab_knowledge_graph` has a
  tested FastAPI/CLI equivalent now.
- **`streamlit_app_.py`** (repo root) and **`streamlit_app_lang_localization.py`** (repo root) —
  both still under author investigation as of Stage 16, not yet triaged; see §5 for what was found.

**Supporting:**
- **`utils/`** — grab-bag of app helpers: `config_loader_short.py`/`config_loader_long.py` (read
  `config/config.ini` and `config/config.toml`), `app_utils.py`, `fake_data_generator/`,
  `project_audit/`, `plotly/`, `rag_embedding_view.py`.
- **`config/config.ini`** — `[neo4j]`, `[rag]`, `[OLLAMA]`, `[DIRECTORIES]`, `[FILES]`,
  `[EXPERIMENT]` sections. **`config/config.toml`** — Streamlit server settings only.
- **`knowledge/rag/`** — the RAG knowledge-base text files, including the clinical-term files
  flagged in §5.
- **`test_data/`** and **`results/`** — both hold overlapping `lab_export_*.jsonl` files; see §5 for
  the Stage 16 finding (`test_data/` confirmed unused by any code, left as-is by author's choice).
  `results/lab_experiment_results/` is the real, `JSONLStore`-backed output tree;
  `results/pytest_test_results/` is where `tox -e py312` writes its HTML report.
- **`docs/source/`** — Sphinx source (`faq_eng.md`, `faq_ua.md` pulled in via myst-parser);
  `docs/source/_build/` (Sphinx's own default `make html`/`make.bat` output directory) is
  generated output, not source — build there (`make html` from `docs/source/`, or
  `sphinx-build docs/source docs/source/_build/html`), not to a separately-invented `docs/build/`.
