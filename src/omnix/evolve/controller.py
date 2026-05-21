"""Select applicable skills for a rebuild target."""

from __future__ import annotations

from omnix.enrich.common import enriched_text, get_node
from omnix.evolve.skill_bank import Skill, SkillBank
from omnix.graph.store import GraphStore
from omnix.retrieval.vector_index import cosine_similarity, embed_text


def select_skills_for(
    target_program_id: str,
    graph_store: GraphStore,
    skill_bank: SkillBank,
    top_k: int = 3,
) -> list[Skill]:
    node = get_node(graph_store, target_program_id)
    signature = enriched_text(node) if node is not None else target_program_id
    target_embedding = embed_text(signature)
    candidates = [skill for skill in skill_bank.get_active() if _matches(skill, signature)]
    scored = []
    for skill in candidates:
        emb = skill.embedding or embed_text(skill.description)
        scored.append((cosine_similarity(target_embedding, emb), skill))
    return [skill for _score, skill in sorted(scored, key=lambda item: (-item[0], item[1].skill_id))[:top_k]]


def _matches(skill: Skill, signature: str) -> bool:
    pred = skill.match_predicate
    contains = pred.get("contains") or pred.get("program_type") or pred.get("byte_diff_pattern")
    return not contains or str(contains).lower() in signature.lower()
