"""
core.adapters.neo4j_repo
============================

:class:`~core.domain.interfaces.GraphRepository` implementation over Neo4j (``py2neo``) -- the
failure-mode/cascade-lineage graph, promoted into the layered architecture 2026-09-05 by explicit
author decision (see :class:`~core.domain.interfaces.GraphRepository`'s own docstring for the full
scope/boundary: this covers only the failure-mode graph, not the original Archetype/Bias
co-occurrence graph or the PageRank scripts, which remain on their existing Streamlit code path).

Every Cypher string and the row-building logic below is ported directly from the already-verified
queries in ``core/tabs/knowledge_graph.py`` (real proof captured against a live Neo4j+GDS install --
see ``docs/source/wiki/07-knowledge-graph-results.rst``), not redesigned from scratch. One real
change from the Streamlit version: ``run_id`` is now an explicit parameter to
:meth:`Neo4jGraphRepo.sync_failure_mode_graph` rather than a column injected into a pandas
DataFrame beforehand -- this adapter takes plain ``list[dict]`` responses (the same shape
:meth:`~core.domain.interfaces.Repository.load_responses` returns), no pandas dependency needed.

Deliberately does **not** import anything from ``core/service/`` or ``core/tabs/`` (the untouched
legacy subsystem, CLAUDE.md SS1) -- reads its own Neo4j credentials directly from
``config/config.ini``'s ``[neo4j]`` section rather than reusing
``core.service.neo4j_service.Neo4jService``, keeping this new architecture layer independent of the
legacy one its one covered capability was promoted out of.

2026-09-05, later the same day: :meth:`Neo4jGraphRepo.behavioral_communities` adds Stage 4 of
``docs/source/wiki/08-graph-representation-learning.rst`` -- the first design-doc technique to
graduate into real code, exactly the growth room the promotion above was for.
"""

import configparser
import re
from pathlib import Path
from typing import Optional

from loguru import logger
from py2neo import Graph

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _ROOT_DIR / "config" / "config.ini"

# Stage 3 (originally): a tiny, fixed pipeline-shape reference subgraph (4 nodes, 3 edges, ever)
# encoding the cascade's own literal stage order -- run once, idempotent (MERGE), so "where does
# the chain terminate" can be answered by real graph traversal (see
# _ROOT_CAUSE_TERMINAL_STAGE_CYPHER) instead of an application-side CASE-based rank lookup dressed
# up as a query.
_BOOTSTRAP_CASCADE_STAGES_CYPHER = """
    MERGE (s0:CascadeStage {name:"Layer0"})
    MERGE (s1:CascadeStage {name:"Layer1"})
    MERGE (s2:CascadeStage {name:"Layer2"})
    MERGE (s3:CascadeStage {name:"Judge"})
    MERGE (s0)-[:PRECEDES]->(s1)
    MERGE (s1)-[:PRECEDES]->(s2)
    MERGE (s2)-[:PRECEDES]->(s3)
"""

# Note: every CascadeStage/CascadeOutcome node is MERGEd as its own bound variable BEFORE any
# relationship to it is merged -- MERGEing a full (node)-[:REL]->(anonymous pattern) in one step
# does NOT reuse an existing node for the anonymous side, it silently creates a duplicate (a real
# Neo4j MERGE pitfall, caught by testing this against the live database before it was first written,
# not assumed correct from the syntax alone).
_SYNC_FAILURE_MODE_CYPHER = """
    UNWIND $rows AS row
    MERGE (resp:Response {response_id: row.response_id})
      SET resp.word_count = row.word_count, resp.duration_ms = row.duration_ms
    MERGE (run:Run {run_id: row.run_id})
    MERGE (resp)-[:IN_RUN]->(run)
    MERGE (arch:Archetype {name: row.archetype})
    MERGE (resp)-[:CONDITIONED_ON]->(arch)
    MERGE (bias:Bias {name: row.bias})
    MERGE (resp)-[:CONDITIONED_ON]->(bias)
    MERGE (student:Model {name: row.student})
    MERGE (resp)-[:GENERATED_BY]->(student)

    MERGE (l0stage:CascadeStage {name: "Layer0"})
    MERGE (l0:CascadeOutcome {stage: "Layer0", result: row.layer0_classification})
    MERGE (l0)-[:PART_OF]->(l0stage)
    MERGE (resp)-[:REACHED]->(l0)

    FOREACH (_ IN CASE WHEN row.reached_layer1 THEN [1] ELSE [] END |
      MERGE (l1stage:CascadeStage {name: "Layer1"})
      MERGE (l1:CascadeOutcome {stage: "Layer1", result: row.layer1_result})
      MERGE (l1)-[:PART_OF]->(l1stage)
      MERGE (resp)-[rl1:REACHED]->(l1)
      SET rl1.score = row.semantic_overlap
    )

    FOREACH (_ IN CASE WHEN row.reached_layer2 THEN [1] ELSE [] END |
      MERGE (l2stage:CascadeStage {name: "Layer2"})
      MERGE (l2:CascadeOutcome {stage: "Layer2", result: row.layer2_result})
      MERGE (l2)-[:PART_OF]->(l2stage)
      MERGE (resp)-[rl2:REACHED]->(l2)
      SET rl2.score = row.layer2_contradiction_score
    )

    FOREACH (_ IN CASE WHEN row.reached_judge THEN [1] ELSE [] END |
      MERGE (judge:Model {name: row.teacher})
      MERGE (resp)-[:JUDGED_BY]->(judge)
      MERGE (judgeStage:CascadeStage {name: "Judge"})
      MERGE (jo:CascadeOutcome {stage: "Judge", result: row.judge_result})
      MERGE (jo)-[:PART_OF]->(judgeStage)
      MERGE (resp)-[rj:REACHED]->(jo)
      SET rj.confidence = row.v_confidence
    )

    FOREACH (chunk IN row.chunks |
      MERGE (kc:KnowledgeChunk {archetype: chunk.archetype, category: chunk.category})
      MERGE (resp)-[:RETRIEVED]->(kc)
    )
"""

# Root-cause query 1: which model is disproportionately linked to echo-rejections, across every
# archetype/bias it was tried against -- a real multi-hop pattern match, not a pandas groupby,
# because it composes for free with any other relationship on Response (archetype, bias, run, ...).
_ROOT_CAUSE_ECHO_BY_MODEL_CYPHER = """
    MATCH (r:Response)-[:GENERATED_BY]->(m:Model),
          (r)-[:REACHED]->(:CascadeOutcome {stage:"Layer1", result:"ECHO"})
    RETURN m.name AS model, count(r) AS echo_count
    ORDER BY echo_count DESC
"""

# Root-cause query 2: for one archetype, where does the cascade chain actually terminate -- using
# the pipeline-shape subgraph (CascadeStage/PRECEDES) via a real EXISTS{} graph traversal, not an
# application-side stage-rank lookup. A response with no *later*-stage REACHED outcome is, by
# construction, terminal at the outcome this query returns.
_ROOT_CAUSE_TERMINAL_STAGE_CYPHER = """
    MATCH (a:Archetype {name:$archetype})<-[:CONDITIONED_ON]-(r:Response)
    MATCH (r)-[:REACHED]->(o:CascadeOutcome)-[:PART_OF]->(s:CascadeStage)
    WHERE NOT EXISTS {
      MATCH (s)-[:PRECEDES]->(:CascadeStage)<-[:PART_OF]-(o2:CascadeOutcome)<-[:REACHED]-(r)
    }
    RETURN o.stage AS terminal_stage, o.result AS terminal_result, count(r) AS n
    ORDER BY n DESC
"""

# Root-cause query 3: which RAG-retrieved knowledge categories are upstream of Layer-1 echo
# failures -- connects the RAG subsystem and the knowledge graph, which never referenced each other
# before this.
_ROOT_CAUSE_RAG_CHUNKS_BY_ECHO_CYPHER = """
    MATCH (c:KnowledgeChunk)<-[:RETRIEVED]-(r:Response)-[:REACHED]->(:CascadeOutcome {stage:"Layer1", result:"ECHO"})
    RETURN c.archetype AS chunk_archetype, c.category AS chunk_category, count(r) AS echo_count
    ORDER BY echo_count DESC
"""

# Stage 4 of docs/source/wiki/08-graph-representation-learning.rst: structural community detection.
# Archetype/Bias/Model/CascadeOutcome are never directly connected in the base schema -- they only
# ever meet through a shared Response (via CONDITIONED_ON/GENERATED_BY/REACHED). This materializes
# that shared-Response co-occurrence as a real, weighted CO_OCCURS_WITH edge (idempotent MERGE, so
# re-running after more responses sync just refreshes the weights) -- the graph GDS actually needs
# to embed/cluster these four node types at all. a/b are bound variables, not the anonymous-MERGE
# pitfall documented above; id(a) < id(b) keeps one edge per pair instead of both directions.
_MATERIALIZE_COOCCURRENCE_CYPHER = """
    MATCH (r:Response)-[:CONDITIONED_ON|GENERATED_BY|REACHED]->(a)
    MATCH (r)-[:CONDITIONED_ON|GENERATED_BY|REACHED]->(b)
    WHERE id(a) < id(b)
    WITH a, b, count(DISTINCT r) AS weight
    MERGE (a)-[co:CO_OCCURS_WITH]->(b)
    SET co.weight = weight
"""

_GRAPH_NAME = "behavioral-communities"

# gds.graph.project's 3-arg native form -- confirmed against the live install (SHOW PROCEDURES),
# not assumed from GDS docs alone: (graphName, nodeProjection, relationshipProjection).
_DROP_GRAPH_IF_EXISTS_CYPHER = "CALL gds.graph.drop($graph_name, false) YIELD graphName"
_PROJECT_GRAPH_CYPHER = """
    CALL gds.graph.project(
        $graph_name,
        ['Archetype', 'Bias', 'Model', 'CascadeOutcome'],
        {CO_OCCURS_WITH: {orientation: 'UNDIRECTED', properties: 'weight'}}
    )
"""

# Community detection runs directly on CO_OCCURS_WITH topology/weights (Leiden's actual input,
# real GDS procedure signature -- gds.leiden.stream does not accept a raw embedding vector, despite
# the wiki page's original "run Leiden on the resulting embedding space" phrasing; corrected there
# alongside this). gds.fastRP.stream is run separately over the same projection, real structural
# embeddings available for the still-open Stage 5/6 techniques (node similarity via gds.knn, link
# prediction) -- not consumed by Leiden itself.
_LEIDEN_STATS_CYPHER = """
    CALL gds.leiden.stats($graph_name, {relationshipWeightProperty: 'weight'})
    YIELD communityCount, modularity
    RETURN communityCount AS community_count, modularity AS modularity
"""
_LEIDEN_STREAM_CYPHER = """
    CALL gds.leiden.stream($graph_name, {relationshipWeightProperty: 'weight'})
    YIELD nodeId, communityId
    WITH gds.util.asNode(nodeId) AS node, communityId
    RETURN communityId AS community_id,
           labels(node)[0] AS node_type,
           CASE WHEN labels(node)[0] = 'CascadeOutcome'
                THEN node.stage + ':' + node.result
                ELSE node.name END AS name
    ORDER BY community_id, node_type, name
"""


def _parse_rag_chunks(rag_context: Optional[str]) -> list[dict]:
    """Recovers structured (archetype, category) chunk provenance from the concatenated
    ``rag_context`` string :meth:`core.services.experiment_runner.ExperimentRunner._run_one`
    persists -- no separate structured chunk list is stored on the response record, so this parses
    the exact serialization format that code writes
    (``f"[{c['archetype']} | {c['category']}]\\n{c['text']}"``, blocks joined by ``"\\n\\n"``).
    A real, disclosed simplification: this collapses every chunk sharing the same
    (archetype, category) pair into one graph node, not one node per distinct chunk of text --
    good enough for "which category of reference material" provenance, not full per-chunk lineage.
    """
    if not isinstance(rag_context, str) or not rag_context.strip():
        return []
    chunks = []
    for block in rag_context.split("\n\n"):
        m = re.match(r"^\[(.+?) \| (.+?)\]\n", block)
        if m:
            chunks.append({"archetype": m.group(1), "category": m.group(2)})
    return chunks


def _build_failure_mode_rows(responses: list[dict], run_id: str) -> list[dict]:
    """Converts one run's plain-dict responses into the row shape ``_SYNC_FAILURE_MODE_CYPHER``
    expects -- in particular, resolves which cascade stages a response actually *reached*.

    A Layer-0-rejected or Layer-1-echo-rejected response never reaches a real judge call (see
    ``ExperimentRunner._run_one``'s early-return at the Layer-0 check, and the ``echo_detected``
    branch that synthesizes a verdict without calling ``self._judge.evaluate(...)``) -- attributing
    that auto-cascade-fail to whichever model happened to be *configured* as judge would misrepresent
    what actually happened, the same class of naming-vs-meaning gap already found twice elsewhere in
    this project (``semantic_overlap``, the benchmark leaderboard's ``mimicry_score``). So
    ``reached_judge`` is computed here, not assumed true just because a ``teacher``/``v_ok`` field
    exists on every row (it does, even for cascade-auto-fails -- CLAUDE.md SS4's own persisted-field
    contract).
    """
    rows = []
    for r in responses:
        layer0 = r.get("layer0_classification")
        layer0 = layer0 if isinstance(layer0, str) and layer0 else "VALID"
        reached_layer1 = layer0 == "VALID"
        echo = bool(r.get("layer1_echo_detected")) if reached_layer1 else False
        reached_judge = reached_layer1 and not echo
        layer2_checked = bool(r.get("layer2_checked"))

        def _num(key: str) -> Optional[float]:
            v = r.get(key)
            return float(v) if v is not None else None

        rows.append(
            {
                "response_id": f"{run_id}:{r.get('step')}",
                "run_id": run_id,
                "archetype": r.get("archetype"),
                "bias": r.get("bias"),
                "student": r.get("student"),
                "teacher": r.get("teacher"),
                "word_count": _num("word_count"),
                "duration_ms": _num("duration_ms"),
                "layer0_classification": layer0,
                "reached_layer1": reached_layer1,
                "layer1_result": "ECHO" if echo else "CLEAN",
                "semantic_overlap": _num("semantic_overlap"),
                "reached_layer2": layer2_checked,
                "layer2_result": r.get("layer2_predicted_label") if layer2_checked else None,
                "layer2_contradiction_score": _num("layer2_contradiction_score"),
                "reached_judge": reached_judge,
                "judge_result": "PASS" if bool(r.get("v_ok")) else "FAIL",
                "v_confidence": _num("v_confidence"),
                "chunks": _parse_rag_chunks(r.get("rag_context")) if r.get("rag_enabled") else [],
            }
        )
    return rows


class Neo4jGraphRepo:
    """See :class:`core.domain.interfaces.GraphRepository`.

    Parameters
    ----------
    graph : py2neo.Graph, optional
        An already-connected graph (for tests -- pass a fake/mock). If omitted, a real connection
        is opened lazily on first use, from ``config/config.ini``'s ``[neo4j]`` section -- not at
        construction time, matching this project's established lazy-singleton pattern for other
        heavyweight/external resources (the sentence embedder, the NLI cross-encoder).
    """

    def __init__(self, graph: Optional[Graph] = None) -> None:
        self._graph = graph

    def _get_graph(self) -> Graph:
        if self._graph is None:
            config = configparser.ConfigParser()
            config.read(_CONFIG_PATH)
            uri = config["neo4j"]["uri"]
            logger.info(f"Neo4jGraphRepo connecting to {uri}")
            self._graph = Graph(uri, auth=(config["neo4j"]["user"], config["neo4j"]["password"]))
        return self._graph

    def sync_failure_mode_graph(self, run_id: str, responses: list[dict]) -> int:
        """See :meth:`core.domain.interfaces.GraphRepository.sync_failure_mode_graph`."""
        graph = self._get_graph()
        graph.run(_BOOTSTRAP_CASCADE_STAGES_CYPHER)
        rows = _build_failure_mode_rows(responses, run_id)
        if rows:
            graph.run(_SYNC_FAILURE_MODE_CYPHER, rows=rows)
        return len(rows)

    def echo_rejections_by_model(self) -> list[dict]:
        """See :meth:`core.domain.interfaces.GraphRepository.echo_rejections_by_model`."""
        return self._get_graph().run(_ROOT_CAUSE_ECHO_BY_MODEL_CYPHER).data()

    def terminal_stage_by_archetype(self, archetype: str) -> list[dict]:
        """See :meth:`core.domain.interfaces.GraphRepository.terminal_stage_by_archetype`."""
        return self._get_graph().run(_ROOT_CAUSE_TERMINAL_STAGE_CYPHER, archetype=archetype).data()

    def rag_chunks_linked_to_echo(self) -> list[dict]:
        """See :meth:`core.domain.interfaces.GraphRepository.rag_chunks_linked_to_echo`."""
        return self._get_graph().run(_ROOT_CAUSE_RAG_CHUNKS_BY_ECHO_CYPHER).data()

    def behavioral_communities(self) -> dict:
        """See :meth:`core.domain.interfaces.GraphRepository.behavioral_communities`."""
        graph = self._get_graph()
        graph.run(_MATERIALIZE_COOCCURRENCE_CYPHER)
        graph.run(_DROP_GRAPH_IF_EXISTS_CYPHER, graph_name=_GRAPH_NAME)
        graph.run(_PROJECT_GRAPH_CYPHER, graph_name=_GRAPH_NAME)
        try:
            stats = graph.run(_LEIDEN_STATS_CYPHER, graph_name=_GRAPH_NAME).data()[0]
            rows = graph.run(_LEIDEN_STREAM_CYPHER, graph_name=_GRAPH_NAME).data()
        finally:
            graph.run(_DROP_GRAPH_IF_EXISTS_CYPHER, graph_name=_GRAPH_NAME)
        return {
            "modularity": stats["modularity"],
            "community_count": stats["community_count"],
            "rows": rows,
        }
