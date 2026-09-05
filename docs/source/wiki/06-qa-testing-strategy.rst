06 — QA: Testing as the Product, Not an Afterthought
========================================================

CLAUDE.md SS7 states this plainly: because this project demonstrates *testing* competence, the test
suite is not a quality gate bolted onto the side of the work, it is one of the things being
demonstrated. This page is not a duplicate of :doc:`../qa` (that page is the exhaustive, generated
roster -- every test file, every test name, the coverage number, the traceability matrix). This page
is the *why* behind that roster: what testing approaches are actually used, why those and not the
obvious alternatives, and where the discipline the rest of this wiki keeps citing ("measurement
validity") shows up concretely in how tests get written.

Why this test taxonomy, specifically
------------------------------------------

``tests/`` splits into ``unit/``, ``integration/``, ``e2e/``, and ``legacy_rag/`` -- not an
arbitrary grouping. :doc:`02-tools-and-stack` covers the concrete bug (a real
``pytest-playwright``/``asyncio`` interaction) that forced ``e2e`` into total process isolation from
the rest of the suite; that same page covers why ``legacy_rag`` stays a separate category rather than
folding into ``unit`` or ``integration`` -- it hits a real embeddings/FAISS engine, not fakes, which
is a materially different testing posture than the other two categories. ``unit`` vs. ``integration``
is the more ordinary split (fakes/mocks vs. a real ``TestClient``-driven FastAPI app), but it is
enforced consistently: every router's fake-swapping fixture pattern described in
:doc:`01-architecture` lives in ``integration/``, and every test exercising a service or adapter
directly against hand-written fakes -- with zero FastAPI import in the file at all -- lives in
``unit/``. That last property is checked directly in :doc:`01-architecture`'s own audit of
``tests/unit/test_experiment_runner.py``, not just asserted: the file that's supposed to be
framework-free genuinely is.

Pinned-fixture tests for borrowed math -- not just business logic
--------------------------------------------------------------------------

CLAUDE.md SS7 is explicit that a metric imported from a third-party library, or computed by
hand-rolled formula, is not assumed correct for this project's use -- it gets pinned against a known
expected value on a fixed input, the same way business logic does. :doc:`04-llm-analytics` already
covers ``zipf_deviation`` (RMSE against a hand-computed expected curve) and
``compute_fit_indices`` (Silhouette/Davies-Bouldin pinned on two perfectly separated synthetic
clusters, where the correct answer is known in advance) as the clearest existing examples.

Two fresh examples exist as a **direct product of this same page's own audit process**, not
retroactively cited: fixing ``semantic_overlap`` (:doc:`04-llm-analytics` covers what was wrong with
it) required a new pinned test file
(``tests/unit/test_calculate_advanced_linguistic_metrics.py``) asserting that near-paraphrase
sentence pairs score a high similarity and genuinely unrelated pairs score low -- not just that the
function returns *some* float without erroring. Fixing ``cognitive_load``'s unnormalized-average
problem (also :doc:`04-llm-analytics`) required a second new file
(``tests/unit/test_neuro_metrics.py``) with an exact hand-computed expected value on a fixed input
(one 4-word sentence, one subordinator, one punctuation mark -- worked out by hand to ``0.2``, then
confirmed the code produces exactly that), plus a saturation test proving the sentence-length cap
actually caps rather than merely existing in a comment. Both modules had **no dedicated test file at
all** before these fixes -- confirmed by direct search, not assumed -- despite computing metrics
persisted on every single response the whole application generates. Finding and closing that gap is
the same discipline CLAUDE.md SS7 asks for, exercised on the spot, not just described in the abstract.

Regression-fence tests: a distinct pattern from "this is correct"
--------------------------------------------------------------------------

Most tests in this suite assert correct behavior. One pattern in the suite deliberately does the
opposite, and it's worth naming as its own category rather than reading it as a mistake: a
**regression fence** pins *today's known-wrong* behavior on purpose, so that behavior can't drift
further without a test noticing, without that test being mistaken for a claim that the behavior is
right. The clearest example lived, until 2026-08-24, in
``tests/unit/test_naive_judge.py::test_malformed_input_pins_the_existing_bug_as_a_regression_fence``
-- its own name and docstring said exactly what it was: "pins TODAY'S WRONG BEHAVIOUR deliberately...
it is a regression fence, not a correctness claim." This pattern existed specifically because
``NaiveJudge`` was CLAUDE.md's explicitly-marked author-swap boundary (SS4/SS6) -- the test's job was
to make sure nobody, including an AI coding agent working elsewhere in the codebase, silently "fixed"
the judge's parsing behavior as a side effect of an unrelated task.

That fence did get rewritten, as part of finally building the real structured judge -- see
:doc:`04-llm-analytics` for the full story of the fix and CLAUDE.md SS4 for the permanent record of
the author's explicit decision to lift this boundary. ``test_naive_judge.py`` was deleted alongside
``core/adapters/naive_judge.py``; ``tests/unit/test_structured_judge.py`` replaces it, and its
malformed-input test (``test_malformed_json_response_falls_back_to_a_distinguishable_false``) now
asserts *correct* behavior -- the malformed case resolves to a distinguishable ``rationale``, not the
old silent, indistinguishable ``verdict=False``. This is the regression-fence pattern doing exactly
what it exists for: the fence held until the real fix landed by deliberate decision, not by an
unrelated edit quietly drifting past it.

Coverage: measured for real, with a stated, deliberate exclusion
------------------------------------------------------------------------

``.coveragerc`` omits exactly three files from the coverage measurement:
``core/service/neo4j_service.py``, ``core/tabs/knowledge_graph.py``,
``utils/other/neo4j_services.py`` -- the Neo4j/knowledge-graph subsystem CLAUDE.md SS1 puts out of
scope "not even import-path-touched." This is a deliberate, narrow exclusion stated in one config
file, not a broad carve-out -- everything else in ``core/``, ``api/``, ``cli/``, ``web/``, ``utils/``
is measured, and :doc:`../qa` reports the real resulting percentage rather than an aspirational one.
Reporting a 0%-covered number on code nobody is supposed to touch would be noise, not signal; the
exclusion is stated explicitly here and in ``.coveragerc`` itself specifically so it reads as a
documented decision, not a hidden gap discovered later.

What "code-verification approach" does *not* yet mean here
--------------------------------------------------------------------

Consistent with :doc:`02-tools-and-stack` and :doc:`05-cicd`: ``mypy`` and ``black`` are pinned dev
dependencies with no project config file and no CI enforcement today -- real findings from ad hoc
``mypy`` runs during specific stages of this project's build got fixed properly rather than
suppressed (:doc:`02-tools-and-stack` lists concrete examples), but nothing runs either tool
automatically on every change yet. Property-based testing (e.g. Hypothesis) for the linguistic
metric functions is not implemented -- pinned-fixture tests catch regressions on the specific
examples chosen, not the wider space of inputs a property-based test would explore. Both are named
directly in :doc:`../qa`'s own "Suggested future QA additions" section as real, disclosed gaps, not
silently absent.
