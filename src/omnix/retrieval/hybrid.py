"""Public hybrid retrieval entry point."""

from __future__ import annotations

from omnix.enrich.common import enriched_text, get_node, has_enrichment
from omnix.graph.store import GraphStore
from omnix.retrieval.bm25_index import Bm25Index
from omnix.retrieval.graph_walker import walk_from
from omnix.retrieval.reranker import rerank, rerank_mode
from omnix.retrieval.rrf import reciprocal_rank_fusion
from omnix.retrieval.token_packer import PackedBundle, pack_into_budget
from omnix.retrieval.vector_index import VectorIndex


def retrieve(
    graph_store: GraphStore,
    target_node_id: str,
    *,
    budget_tokens: int = 30000,
    hop_depth: int = 4,
    edge_types: tuple[str, ...] = ("COPIES", "CALLS", "PERFORMS", "READS", "WRITES", "DEFINES", "INVOKES"),
) -> PackedBundle:
    target = get_node(graph_store, target_node_id)
    query_text = enriched_text(target) if target else target_node_id
    bm25 = Bm25Index(graph_store).query(query_text, top_k=40)
    graph_hits = walk_from(graph_store, target_node_id, list(edge_types), max_depth=hop_depth, max_nodes=200)
    vector: list[tuple[str, float]] = []
    if has_enrichment(target) or any(has_enrichment(get_node(graph_store, node_id)) for node_id, _ in graph_hits):
        try:
            vector = VectorIndex(graph_store).query(query_text, "programs", top_k=40)
        except (ValueError, RuntimeError):
            vector = []

    rankings = [
        [node_id for node_id, _score in bm25],
        [node_id for node_id, _distance in vector],
        [node_id for node_id, _hop in graph_hits],
    ]
    fused = reciprocal_rank_fusion([ranking for ranking in rankings if ranking])
    scores = dict(fused)
    content = []
    for node_id, _score in fused:
        node = get_node(graph_store, node_id)
        if node is not None:
            content.append((node_id, enriched_text(node) or node.name))
    if target is not None and target.id not in {node_id for node_id, _ in content}:
        content.insert(0, (target.id, enriched_text(target) or target.name))
    rerank_count = 0
    if content and rerank_mode() != "off":
        candidates = content[:20]
        ranked = rerank(query_text, [text for _node_id, text in candidates], top_n=min(10, len(candidates)))
        content = [candidates[idx] for idx, _score in ranked if idx < len(candidates)]
        rerank_count = len(candidates)
    retrieval_modes = {
        "bm25": len(bm25),
        "vector": len(vector),
        "graph": len(graph_hits),
    }
    if rerank_count:
        retrieval_modes["rerank"] = rerank_count
    return pack_into_budget(
        content,
        budget_tokens,
        scores=scores,
        retrieval_modes=retrieval_modes,
    )
