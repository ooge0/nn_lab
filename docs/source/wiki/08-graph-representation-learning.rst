08 — Beyond Hand-Written Queries: Graph Representation Learning as a Higher Abstraction Layer
====================================================================================================

Why this page exists
-------------------------

:doc:`07-knowledge-graph-results` gave the failure-mode graph real, working root-cause queries --
but all three are Cypher someone had to already think to write. They can confirm a suspected
pattern ("does model X echo more than model Y") but cannot surface a pattern nobody thought to look
for. This page is the theoretical grounding for the next layer up: using the graph's own *structure*
-- not hand-picked Cypher -- to generate candidate patterns, flag structural outliers, and predict
risk for combinations never actually run. That's the concrete meaning behind "give the system a
sense for it" -- not a vague aspiration, but a named, 20-to-60-year-old academic subfield per
technique below, each with a real paper cited, not invented for this page.

This is a **design document for future work, not yet built** -- same status as
:doc:`05-cicd`'s "current absence + concrete target pipeline" framing. Nothing on this page requires
a new dependency: every GDS procedure named below was confirmed **live, on the actual local
install**, not assumed from documentation (see *Confirmed available now* below).

The gap, precisely
-----------------------

The existing corpus-level analysis (CLAUDE.md SS3b, :doc:`../architecture`'s clustering pipeline)
already does real unsupervised structure-finding -- UMAP + HDBSCAN over the *linguistic feature
matrix* (cognitive load, lexical density, etc.). The failure-mode graph (:doc:`07-knowledge-graph-results`)
adds a second, independent data source: *relational* structure -- which archetype/bias/model/RAG-chunk
nodes are connected to which cascade outcomes. Nothing today combines these two views. That's the
actual gap: two independently valid ways of asking "what's similar to what" that have never been
cross-checked against each other.

Four techniques, each grounded in a real, cited source
------------------------------------------------------------

**1. Structural node embeddings (FastRP, GDS-native).** Represent every node (Archetype, Bias,
Model, CascadeOutcome, KnowledgeChunk) as a vector derived purely from its position in the graph --
not from any linguistic feature. The foundational method for this is node2vec (biased random
walks + skip-gram) [Grover2016]_. This project's actual choice is **FastRP**, not node2vec directly:
Neo4j's own benchmarking reports FastRP as "up to 75,000 times faster than Node2Vec with equivalent
accuracy" [Neo4jFastRP]_, and FastRP's own theoretical grounding (very sparse random projection,
backed by the Johnson-Lindenstrauss lemma) is a real, separate, cited result [Chen2019]_ -- not a
Neo4j marketing claim taken on faith. This specific tradeoff -- 5 orders of magnitude cheaper for
"equivalent accuracy" -- is exactly what CLAUDE.md's own standing "weak machine" constraint calls
for, the same reasoning that picked ``all-MiniLM-L6-v2``/``nli-MiniLM2-L6-H768`` over larger models
elsewhere in this project.

**2. Community detection (Leiden, not Louvain).** Cluster the embedded graph into "behavioral
communities" -- groups of archetype/bias/model/outcome nodes that are more densely connected to
each other than to the rest of the graph. The obvious default, Louvain [Blondel2008]_, has a real,
measured defect: its own successor paper found Louvain "may yield arbitrarily badly connected
communities... in experimental analysis, up to 25% of the communities are badly connected and up to
16% are disconnected" [Traag2019]_. Leiden fixes this with a provable well-connectedness guarantee
and is the direct GDS-native replacement -- picking Leiden over Louvain here is itself a real,
citable measurement-validity decision, the same kind of threshold-inversion-caliber finding this
project already has a track record of making (see :doc:`04-llm-analytics`'s Layer 1 story), not a
default accepted without checking.

**3. Cross-validating the two clustering views (methodological triangulation).** Once Leiden
produces graph-structural communities, compare them against the existing UMAP/HDBSCAN
feature-based clusters over the *same* corpus. This is not a novel idea invented for this
project -- it is the multitrait-multimethod matrix, Campbell & Fiske's 1959 foundational argument
that a construct's validity is strengthened when *independent measurement methods* converge, and
that divergence between methods is itself informative, not noise to explain away
[CampbellFiske1959]_. Concretely: agreement between the two clusterings (measurable via e.g.
normalized mutual information) is real convergent evidence that a behavioral grouping reflects
something structural, not an artifact of one particular metric space; disagreement flags archetypes
that look similar linguistically but sit in different relational neighborhoods (or vice versa) --
a genuinely new finding neither method alone could produce.

**4. Structural anomaly / analogy detection (node similarity).** Run ``gds.nodeSimilarity`` over the
FastRP embeddings to answer two symmetric questions directly: "what is this archetype/bias/model
structurally most like" (an automatic analogy -- the literal mechanism behind "this reminds me
of..."), and, at the low-similarity extreme, "what does this resemble nothing else in the corpus"
-- a real structural anomaly, in the sense formalized by the graph-anomaly-detection literature
[Akoglu2015]_. This is a meaningfully different anomaly signal than a simple high-failure-rate flag:
a node can have an entirely ordinary pass rate while still having a structurally unusual *pattern*
of which cascade stages it reaches, which nothing in the current failure-mode queries would surface.

**5. Link prediction for untried combinations.** Given the graph of (archetype, bias, model) triples
already run, predict which *untried* combinations are likely to land on a negative
``CascadeOutcome`` -- before spending real Ollama time generating them. Link prediction is a
20-year-old, well-established subfield, not a speculative idea: Liben-Nowell & Kleinberg's
foundational formalization asks exactly this question ("given a snapshot of a network, which new
connections are likely to form") using pure topology [LibenNowell2007]_; modern knowledge-graph-
specific approaches (embedding-based link prediction, surveyed comprehensively as of 2024
[Wang2024]_) extend this to typed, multi-relational graphs -- exactly this project's schema
(``CONDITIONED_ON``/``GENERATED_BY``/``REACHED`` are distinct relation types, not one flat edge).
This is the most literal reading of "give the system a sense for it": a real predicted-risk score
for a combination that has never actually been generated.

Confirmed available now, not assumed
------------------------------------------

Checked directly against the live local install (the same one :doc:`07-knowledge-graph-results`
fixed and verified), not taken from documentation alone:

.. list-table::
   :widths: 55 20 25
   :header-rows: 1

   * - Procedure
     - Available
     - Use above
   * - ``gds.fastRP.stream``
     - ✅ yes
     - Technique 1 (structural embeddings)
   * - ``gds.node2vec.stream``
     - ✅ yes (available, but FastRP is the recommended default -- see above)
     - Technique 1, alternative
   * - ``gds.leiden.stream``
     - ✅ yes
     - Technique 2 (community detection)
   * - ``gds.nodeSimilarity.stream``
     - ✅ yes
     - Technique 4 (analogy / anomaly)
   * - ``gds.beta.pipeline.linkPrediction.create``
     - ✅ yes (pipeline API)
     - Technique 5 (link prediction)
   * - ``gds.linkPrediction.train`` / ``gds.alpha.linkprediction.adamicAdar``
     - ❌ not registered on this GDS version
     - Use the pipeline API above instead, not these older/alpha names

A staged plan, building on Stages 1-3 already shipped
------------------------------------------------------------

Each stage below gets a **real validation step**, not "ran the algorithm, eyeballed the output" --
matching the same discipline :func:`core.services.cluster_discovery.compute_fit_indices` already
applies to the existing UMAP/HDBSCAN pipeline.

- **Stage 4 -- structural embeddings + Leiden communities.** Project the failure-mode graph,
  run ``gds.fastRP.stream``, then ``gds.leiden.stream`` on the resulting embedding space.
  *Validate with*: GDS's own reported modularity/conductance for the partition, plus normalized
  mutual information against the existing UMAP/HDBSCAN cluster assignments for the same responses
  (Technique 3) -- report both the agreement score and at least one concrete disagreement case,
  not just the number.
- **Stage 5 -- node similarity for analogy/anomaly.** ``gds.nodeSimilarity.stream`` over the Stage 4
  embeddings. *Validate with*: manual spot-check of the top-3 "most similar" pairs and the single
  most anomalous node against a human read of the underlying real responses -- does the structural
  claim actually hold up, the same "don't trust the algorithm's output as ground truth" discipline
  CLAUDE.md SS7 already applies to borrowed metrics.
- **Stage 6 -- link prediction for untried combinations.** ``gds.beta.pipeline.linkPrediction``
  trained on already-run (archetype, bias, model) triples, evaluated on a real held-out split.
  *Validate with*: precision/recall/AUC on the held-out edges -- and, ideally, an actual follow-up
  experiment run against a small number of the pipeline's highest-predicted-risk untried
  combinations, to see whether the prediction holds against a real new Ollama-generated response,
  not just against historical data.

Honest scope note
----------------------

This remains, explicitly, inside CLAUDE.md SS1's Neo4j quarantine -- a design document for the
*legacy, untouched* subsystem, not a proposal to promote graph representation learning into
``core.domain``/``core.services`` or this project's own testing/architecture discipline. And a
direct caution on the "intuition" framing itself: everything above produces a *score* --
similarity, community assignment, predicted-risk probability -- not a verdict. Treating a
structural-anomaly flag or a link-prediction score as ground truth without the validation step
listed for its stage would repeat exactly the mistake this project already caught once for Layer 1
(an unvalidated intuition about what "should" correlate turned out to be backwards on real data --
see :doc:`04-llm-analytics`). The discipline that makes that story worth telling is checking the
intuition against real data before trusting it, not skipping that step because the technique sounds
sophisticated.

.. rubric:: References

.. [Grover2016] Grover, A., & Leskovec, J. (2016). node2vec: Scalable Feature Learning for
   Networks. *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery
   and Data Mining*, 855-864. https://arxiv.org/abs/1607.00653
.. [Neo4jFastRP] Neo4j Graph Data Science documentation. Fast Random Projection.
   https://neo4j.com/docs/graph-data-science/current/machine-learning/node-embeddings/fastrp/
.. [Chen2019] Chen, H., Sultan, S. F., Tian, Y., Chen, M., & Skiena, S. (2019). Fast and Accurate
   Network Embeddings via Very Sparse Random Projection. *Proceedings of the 28th ACM International
   Conference on Information and Knowledge Management*. https://arxiv.org/abs/1908.11512
.. [Blondel2008] Blondel, V. D., Guillaume, J.-L., Lambiotte, R., & Lefebvre, E. (2008). Fast
   unfolding of communities in large networks. *Journal of Statistical Mechanics: Theory and
   Experiment*, 2008(10).
.. [Traag2019] Traag, V. A., Waltman, L., & van Eck, N. J. (2019). From Louvain to Leiden:
   guaranteeing well-connected communities. *Scientific Reports*, 9, 5233.
   https://arxiv.org/abs/1810.08473
.. [CampbellFiske1959] Campbell, D. T., & Fiske, D. W. (1959). Convergent and discriminant
   validation by the multitrait-multimethod matrix. *Psychological Bulletin*, 56(2), 81-105.
.. [Akoglu2015] Akoglu, L., Tong, H., & Koutra, D. (2015). Graph based anomaly detection and
   description: a survey. *Data Mining and Knowledge Discovery*, 29(3), 626-688.
   https://doi.org/10.1007/s10618-014-0365-y
.. [LibenNowell2007] Liben-Nowell, D., & Kleinberg, J. (2007). The link-prediction problem for
   social networks. *Journal of the American Society for Information Science and Technology*,
   58(7), 1019-1031. https://www.cs.cornell.edu/home/kleinber/link-pred.pdf
.. [Wang2024] Survey coverage of modern knowledge-graph embedding and link-prediction approaches,
   2024. *Knowledge Graph Embeddings: A Comprehensive Survey on Capturing Relation Properties*.
   https://arxiv.org/abs/2410.14733
