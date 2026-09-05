07 — Knowledge Graph: Real Results, Not Just a Design
==========================================================

Why this page exists
-------------------------

A 2026-09-05 audit of the resume-facing claim "implemented RAG-based evaluation workflows" and
"designed a knowledge graph" found the RAG side fully real and end-to-end (see
:doc:`04-llm-analytics`), but the knowledge-graph side had a real, author-disclosed bug: three of
four "PageRank" scripts in :class:`~core.tabs.knowledge_graph.KnowledgeGraph` failed with
``Procedure.ProcedureNotFound`` against this project's own documented Neo4j setup, and the
subsystem had zero automated test coverage. This page is the record of fixing that for real and
capturing genuine output -- so the underlying claim can be defended with a reproducible result, not
just a code walkthrough.

This is a narrow, explicit exception to CLAUDE.md SS1's Neo4j quarantine ("untouched... no
logic/behavior changes... without a separate explicit decision"), made the same way the earlier
judge-fix exception was (SS4/SS6): the author asked for it directly, scoped tightly (a config fix,
one real code bug fix, tests, and this writeup -- not a rewrite, not a move into
``core.domain``/``core.services``), and it's recorded here rather than silently folded in.

Root cause, found by checking the real install, not guessing
------------------------------------------------------------------

``core/tabs/knowledge_graph.py``'s own inline comment already disclosed the symptom::

    # TODO: Need resolve "Error running PageRank script-3: [Procedure.ProcedureNotFound]
    #  There is no procedure with the name gds.graph.exists registered for this database
    #  instance. Please ensure you've spelled the procedure name correctly and that the
    #  procedure is properly deployed."

The natural assumption -- the GDS plugin was never installed -- was wrong. Checking the real local
install (``D:\setup\neo4j\2026.05.0``) directly showed the plugin jar already present and correctly
sized (``plugins/neo4j-graph-data-science-2026.05.0.jar``, 66 MB, next to ``apoc-2026.05.0-core.jar``).
The actual cause was in ``conf/neo4j.conf``::

    dbms.security.procedures.unrestricted=my.extensions.example,my.procedures.*   # never edited
    dbms.security.procedures.allowlist=apoc.*                                     # gds.* missing

Neo4j's procedure sandboxing refuses to register any procedure not explicitly unrestricted and
allowlisted. GDS's jar was loaded but locked out -- exactly what
``Procedure.ProcedureNotFound: gds.graph.exists`` means. This also explains why the bug was never
caught: the README's own "Neo4j setup" section (see ``README.MD``, *Neo4j setup*) walks through
installing plain Neo4j Community Edition and verifying connectivity via ``apoc.help('pageRank')`` --
APOC, a different plugin, which says nothing about whether GDS is actually registered. The
documented setup path never provisioned what the GDS-dependent code needed.

The fix, two lines::

    dbms.security.procedures.unrestricted=gds.*
    dbms.security.procedures.allowlist=apoc.*,gds.*

...followed by a Neo4j restart (``neo4j.bat console`` on Windows). The original ``neo4j.conf`` was
backed up (``neo4j.conf.bak-before-gds-fix``) before editing.

Verified directly, not assumed, immediately after the restart::

    RETURN gds.version()          -> '2026.05.0'
    CALL gds.list() YIELD name    -> 494 procedures registered
    'gds.graph.exists'   in that list -> True
    'gds.graph.project'  in that list -> True
    'gds.pageRank.stream' in that list -> True

A second real bug found and fixed in the same pass
--------------------------------------------------------

Reading all four "PageRank" scripts side by side (not just the one with the disclosed TODO) found
a second, related bug: script-4 called ``gds.pageRank.stream('experimentGraph')`` directly, with no
``gds.graph.exists``/``gds.graph.project`` guard at all -- unlike scripts 1 and 3, which check first.
It only ever "worked" if script-3 happened to run first in the same GDS session, since GDS's graph
catalog lives in server memory and does not persist across a Neo4j restart. Fixed to match the same
exists-check-then-project pattern already used elsewhere in the file (see the inline comment at the
fix site, dated 2026-09-05).

Real end-to-end proof, captured live
-----------------------------------------

Rather than reason about whether the fix worked, the actual, unmodified production code path was
driven end to end: ``streamlit run run_knowledge_graph.py`` (the real, only entry point to this
subsystem per SS12), automated via Playwright against a real run's data
(``run-1788533992004``, 117 responses, 3 archetypes x 3 biases), clicking the real buttons in the
real UI. No mocking, no reimplementation of the app's own logic -- only today's script-4 fix
differs from what a live demo would show.

**1. Sync history to Neo4j** -- real result: *"History synced into Neo4j! 117 rows processed."*

.. image:: /_static/kg_proof/1_sync_success.png
   :alt: Real screenshot of a successful Neo4j sync, 117 rows processed
   :width: 100%

**2. PageRank script-1** (``archetypeGraph``, GDS, previously broken) -- now completes:

.. image:: /_static/kg_proof/2_pagerank1.png
   :alt: Real screenshot of PageRank script-1 completing on archetypeGraph
   :width: 100%

**3. PageRank script-4** (the bug fixed today) -- now completes, proving the fix:

.. image:: /_static/kg_proof/5_pagerank4.png
   :alt: Real screenshot of PageRank script-4 completing on experimentGraph after the fix
   :width: 100%

The full, real PageRank output from both graphs was also pulled directly from Neo4j and saved as
data -- ``results/knowledge_graph_analyses/pagerank_results_2026-09-05.json`` -- rather than relying
on a screenshot alone as the only record.

What the real numbers actually show (and why they're not a bug)
-----------------------------------------------------------------------

After the sync, the graph held **5 Archetype nodes, 6 Bias nodes, 30 ``ASSOCIATED_WITH`` edges** --
more than today's single 3x3 run contributed, because ``MERGE`` is idempotent: the graph
accumulates every run ever synced across sessions (evidenced by pre-existing
``results/graph_data/*.html`` files from an earlier manual session in June). That's the intended
behavior of a knowledge graph as opposed to a per-run JSONL dump -- it's supposed to accumulate.

``archetypeGraph`` (script-1, projects only the ``Archetype`` label): every node scored exactly
``0.15`` -- Neo4j PageRank's damping-factor floor score, ``1 - 0.85``, the value every node gets
when it has no in-graph edges to redistribute rank through. This is real and correctly computed,
not a bug in the fix: projecting a single node label with a relationship type whose other endpoint
(``Bias``) isn't included in the projection leaves every ``ASSOCIATED_WITH`` edge with no target
inside the projected graph, so GDS sees 5 isolated nodes. That's a modeling choice worth naming
honestly (script-1's projection is too narrow to show real centrality), not a defect in the fix.

``experimentGraph`` (scripts 3/4, projects both ``Archetype`` and ``Bias``, undirected): real,
non-trivial scores -- every Archetype node scored ``1.0496``, every Bias node scored ``0.8876``.
The two node types are each internally identical because **30 edges across 5 Archetypes and 6
Biases is exactly a complete bipartite graph** (:math:`K_{5,6}`, 5*6=30) -- every archetype is
connected to every bias. In a complete bipartite graph, PageRank is symmetric within each partition
by graph-theoretic necessity (every node in one side has an identical neighborhood shape), so equal
scores within each side is the *correct*, expected output, not a sign nothing differentiated. The
Archetype/Bias score gap (1.05 vs. 0.89) reflects the two partitions' different sizes (5 vs. 6) --
PageRank on an undirected complete bipartite graph favors the smaller side, which receives
proportionally more incoming rank per node.

Regression coverage added
------------------------------

This subsystem had zero test coverage before this pass (confirmed by a full-repo grep). A live
Neo4j integration test isn't a good fit for CI here -- this project has no Docker and no disposable
test-database story (SS2) -- so :mod:`tests.unit.test_knowledge_graph` instead runs the real
:meth:`KnowledgeGraph.knowledge_graph_tab` headlessly via ``streamlit.testing.v1.AppTest`` against a
fake, in-memory stand-in for ``py2neo.Graph`` that records every Cypher string and parameter sent,
in order. This can't prove GDS itself works (only a live server can, which is what the section
above did, once, for real) -- what it locks in is the *query construction and ordering*, which is
exactly the class of bug found here: 4 tests, including a named regression fence
(``test_pagerank_script_4_now_projects_before_streaming_regression_fence``) that fails loudly if
the exists-check-then-project guard is ever removed from script-4 again.

Honest, disclosed limitations -- still real, still worth naming
-----------------------------------------------------------------------

- **GDS's graph catalog is in-memory and does not survive a Neo4j restart.** Every session, the
  first PageRank script run against a given projection name re-creates it via the exists-check
  guard (now present in all four scripts) -- this is expected GDS behavior, not something to "fix."
- **Tabs 5/6 ("Hypothesis Testing", "Uncertainty Analysis") never touch Neo4j at all** -- confirmed
  by reading the code: both run plain pandas/scipy statistics on the in-memory DataFrame. They are
  visually packaged inside the same Streamlit tab set but are not graph analytics; don't cite them
  as graph-database work.
- **The new unit tests are a query-construction regression fence, not a live-server integration
  test.** They cannot, on their own, prove a real Neo4j+GDS deployment still works after a future
  change -- only a manual run like the one captured above can. That gap is disclosed, not hidden,
  and is a direct consequence of this project's own no-Docker/no-disposable-test-database
  constraint (CLAUDE.md SS2), not an oversight specific to this subsystem.
- This remains, deliberately, outside the FastAPI rewrite's layering (``core.domain`` /
  ``core.services`` / ``core.adapters``) and outside its testing-rigor "moat" (CLAUDE.md SS1/SS6).
  Today's fix makes the existing legacy code actually work and proves it once, live -- it does not
  promote this subsystem into the rewrite's own architecture or ongoing test discipline.

Part 2 — a failure-mode / cascade-lineage graph, and real root-cause queries
--------------------------------------------------------------------------------

The PageRank fix above proved the *existing* Archetype-Bias co-occurrence graph works. It doesn't
answer anything about *why* a response failed -- that graph has no concept of pass/fail at all. A
follow-up request asked directly: what's the most useful thing a graph, specifically, could do for
this project that a table can't? Researched real practice first (data-lineage and AIOps root-cause
literature -- Neo4j's own lineage-graph writeups, an AIOps root-cause-mining paper, graph-based
anomaly-fusion research) rather than inventing a schema from scratch; the answer, consistently: model
the actual pipeline as explicit stage-to-stage lineage edges, not flat labels, so a failure becomes a
graph traversal back through the pipeline instead of a correlation you have to already suspect.

Schema (additive -- a second sync, doesn't touch the original Archetype/Bias/PageRank graph)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every field name below was confirmed directly against ``ExperimentRunner._run_one``'s real
persisted entry shape before writing any Cypher -- not guessed. Node types: ``Response``, ``Run``,
``Archetype``, ``Bias``, ``Model`` (student and judge -- the *same* node in self-critic mode, itself
a real signal), ``CascadeOutcome`` (a small, fixed dictionary of ``{stage, result}`` pairs -- e.g.
``{Layer1, ECHO}`` -- reused by every response that reaches it, not one node per response),
``CascadeStage`` (four fixed reference nodes encoding the pipeline's literal order via
``PRECEDES``), and ``KnowledgeChunk`` (RAG provenance, recovered by parsing the persisted
``rag_context`` string back into ``{archetype, category}`` pairs -- a real, disclosed
simplification: this collapses chunks sharing that pair into one node, not full per-chunk lineage).
A response connects to each ``CascadeOutcome`` it actually reached via a ``REACHED`` relationship
(properties -- score/confidence -- live on the relationship, keeping the outcome dictionary tiny
regardless of corpus size).

**A real Cypher `MERGE` pitfall found and fixed before this shipped**, worth naming since it's easy
to repeat: ``MERGE (l0)-[:PART_OF]->(:CascadeStage {name:"Layer0"})`` looks like it reuses the
already-bootstrapped ``CascadeStage`` node, but it doesn't -- MERGE matches/creates the *whole*
pattern as one unit, and an anonymous node inside it is never looked up against the rest of the
graph. It silently created duplicate ``CascadeStage`` nodes. Confirmed with a synthetic smoke test
against the live database (count went from an expected 4 to more) before this was ever wired into
the app; fixed by MERGEing the ``CascadeStage`` as its own bound variable first, then merging the
relationship to that bound variable.

**A real pipeline-semantics subtlety, found in the actual results, not assumed away:** Layer 2's
hallucination check runs *before* the echo-vs-real-judge branch in ``_run_one`` and is unconditional
on echo status -- so a response can be echo-rejected at Layer 1 *and* still have
``layer2_checked=True``. In the terminal-stage query below, such a response shows ``Layer2`` as its
"terminal" outcome, purely because Layer 2 sits later in the fixed ``PRECEDES`` order -- not because
the pipeline's real gating decision progressed past Layer 1. The real verdict for that response was
still decided (and auto-failed) at Layer 1; Layer 2 is an independent, non-gating side-channel, not
a later gate in the same decision chain. This is disclosed here rather than smoothed over, and is
exactly why :func:`core.tabs.knowledge_graph._build_failure_mode_rows` computes ``reached_judge``
from ``(layer0 == VALID) and (not echo)`` explicitly, rather than assuming "reached Layer 2" implies
"reached the judge."

Real root-cause queries, run against a real 500-response, RAG-enabled run
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Driven the same way as Part 1 -- the real, unmodified (except this addition) production Streamlit
app, via Playwright, against ``run-1787604530235`` (500 responses, RAG enabled on all of them, 3
real Layer-0 ``TRUNCATED`` rejections, 39 real Layer-1 echo detections, 5 archetypes). Full output
saved to ``results/knowledge_graph_analyses/failure_mode_root_cause_2026-09-05.json``.

.. image:: /_static/kg_proof/6_failure_mode_sync.png
   :alt: Real screenshot of the failure-mode graph sync completing on 500 responses
   :width: 100%

**Query 1 -- which model is disproportionately linked to echo-rejections?** Real result:
``mistral:7b-instruct-q4_K_M`` -- 27 echo-rejections; ``qwen:latest`` -- 12. A genuine, actionable
finding: in this run, mistral echoed its own bias/archetype instruction back more than twice as
often as qwen.

.. image:: /_static/kg_proof/7_root_cause_echo_by_model.png
   :alt: Real screenshot of the echo-rejection-by-model root-cause query result
   :width: 100%

**Query 2 -- where does the cascade terminate, per archetype?** (uses the ``CascadeStage``/
``PRECEDES`` subgraph via a real ``EXISTS {}`` traversal, not an application-side rank lookup).
Real result for every archetype in this run showed the same real shape: most responses terminate at
``Judge`` (``PASS`` or ``FAIL``), a real minority terminate earlier -- e.g. ``Defensive`` and
``Structured`` both had 1-2 responses terminate at ``Layer0/TRUNCATED``, and every archetype had
several terminate at ``Layer2`` (the echo-plus-layer2-checked case explained above, not a "reached
further" case).

**Query 3 -- which RAG knowledge categories are upstream of echo-rejections?** The first query in
this codebase connecting the RAG subsystem and the knowledge graph at all -- previously the two
never referenced each other. Real result: the ``paranoid`` archetype's ``Behavior`` category
chunk is linked to 36 echo-rejections, more than double the next-highest category
(``baseline``/``Edge case``, 14). A specific, actionable finding: responses that retrieved
*that* reference material were disproportionately likely to just echo it back instead of
generating new conditioned text.

.. image:: /_static/kg_proof/9_root_cause_rag_chunks.png
   :alt: Real screenshot of the RAG-chunk-category-vs-echo-rejection root-cause query result
   :width: 100%

Regression coverage
~~~~~~~~~~~~~~~~~~~~~~~~

:mod:`tests.unit.test_knowledge_graph` gained 7 more tests (11 total for this module): pure-logic
tests for ``_parse_rag_chunks``/``_build_failure_mode_rows`` covering exactly the pipeline
subtleties above (a Layer-0-rejected response reaches nothing further; an echo-rejected response
can still show ``reached_layer2=True`` but must never show ``reached_judge=True``; RAG chunks parse
only when ``rag_enabled``), plus one ``AppTest``-level test confirming the new "Sync failure-mode
graph" button sends both the bootstrap and the per-response sync Cypher.

Reproducing this yourself
------------------------------

.. code-block:: powershell

   # 1. Start Neo4j (config already fixed, see above)
   D:\setup\neo4j\2026.05.0\bin\neo4j.bat console

   # 2. Start the real app
   streamlit run run_knowledge_graph.py

   # 3. In the browser: pick a run with real archetype/bias variety, click
   #    "Sync history to Neo4j", then any of the four PageRank script buttons --
   #    or the "Root Cause (Failure-Mode Graph)" tab's "Sync failure-mode graph"
   #    button, then any of its three root-cause query buttons.

   # 4. Automated unit coverage (no live server needed):
   pytest tests/unit/test_knowledge_graph.py -v
