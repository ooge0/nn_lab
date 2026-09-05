Engineering Wiki
==================

The rest of this Sphinx build (:doc:`../architecture`, :doc:`../features`, :doc:`../qa`) documents
*what exists* and *what's tested*. This wiki is different: it is the engineering-rationale layer
those pages don't carry -- for each real decision in the codebase, *why that choice and not the
obvious alternative*, grounded in the actual code (file/function citations throughout) rather than
restated as an abstract best practice.

One deliberate exception: :doc:`00-getting-started` is procedural, not rationale -- a practical
"bare checkout to running app, passing tests, real reports" walkthrough, added because a reader
new to the repo needs a *how* before the *why* pages below are useful to them at all.

Read in order -- each page assumes the ones before it:

.. toctree::
   :maxdepth: 2
   :numbered:

   00-getting-started
   01-architecture
   02-tools-and-stack
   03-feature-implementation
   04-llm-analytics
   05-cicd
   06-qa-testing-strategy
   07-knowledge-graph-results
   08-graph-representation-learning

0. :doc:`00-getting-started` -- environment setup from scratch, running every front end, service
   manipulations, tests, reports, and a manual verification checklist.
1. :doc:`01-architecture` -- how the backend and frontend are actually split, what request flow
   looks like end to end, and what the FastAPI rewrite bought over the original Streamlit monolith.
2. :doc:`02-tools-and-stack` -- the stack, one component at a time, each with the alternative it
   beat and why; the coding conventions the project actually enforces.
3. :doc:`03-feature-implementation` -- how the core features are actually wired, and the known
   technical debt/duplication in the current code, named plainly.
4. :doc:`04-llm-analytics` -- the most detailed page: every metric this project computes, grouped by
   level, what's built vs. explicitly not built of the intended evaluation cascade, and where this
   stands against industry-standard LLM-eval technique.
5. :doc:`05-cicd` -- the current, real absence of CI/CD, and a concrete GitHub Actions pipeline
   shaped specifically around this repository's own constraints.
6. :doc:`06-qa-testing-strategy` -- testing approaches actually used and why, distinct from
   :doc:`../qa`'s generated roster: this page is the rationale, that page is the evidence.
7. :doc:`07-knowledge-graph-results` -- a real, disclosed bug in the quarantined Neo4j/GDS
   subsystem, found and fixed under a narrow, explicit exception to CLAUDE.md SS1, with real
   captured proof (screenshots, real PageRank output data) that it now genuinely works -- plus a
   follow-up failure-mode/cascade-lineage graph with real root-cause query results over a real
   500-response run.
8. :doc:`08-graph-representation-learning` -- a design document (not yet built) for the next layer
   up: using the failure-mode graph's own structure -- node embeddings, community detection,
   anomaly/analogy detection, link prediction -- to surface patterns nobody wrote a query for,
   grounded in five real, cited academic sources rather than invented, with every GDS procedure
   named confirmed available on the actual live install.
