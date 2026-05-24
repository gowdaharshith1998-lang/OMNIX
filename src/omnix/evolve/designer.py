"""Designer loop that mints reusable skills from hard cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omnix.enrich.common import call_fabric_provider, parse_jsonish, response_content
from omnix.evolve.hard_case_buffer import HardCaseBuffer
from omnix.evolve.skill_bank import Skill, SkillBank
from omnix.graph.store import GraphStore


@dataclass(frozen=True)
class DesignerReport:
    clusters_examined: int
    skills_minted: int
    cost_usd: float


async def run_designer(
    graph_store: GraphStore,
    hard_case_buffer: HardCaseBuffer,
    fabric_provider: Any,
) -> DesignerReport:
    cases = hard_case_buffer.get_pending_for_designer()
    if len(cases) < 2:
        return DesignerReport(0, 0, 0.0)
    clusters = [cases]
    result = await call_fabric_provider(
        fabric_provider,
        "Return JSON {'skills': [...]} for reusable COBOL rebuild skills from these hard cases: "
        + repr([case.__dict__ for case in cases]),
        model="gpt-4.1",
        json_mode=True,
    )
    content, cost = response_content(result)
    parsed = parse_jsonish(content)
    skills = parsed.get("skills", []) if isinstance(parsed, dict) else []
    bank = SkillBank(graph_store)
    minted = 0
    case_ids = [case.entry_id for case in cases]
    for item in skills:
        if not isinstance(item, dict):
            continue
        bank.add(
            Skill(
                skill_id="",
                title=str(item.get("title") or "COBOL rebuild skill"),
                description=str(item.get("description") or ""),
                match_predicate=dict(item.get("match_predicate") or {}),
                prompt_addendum=str(item.get("prompt_addendum") or ""),
                provenance_hard_cases=case_ids,
            )
        )
        minted += 1
    if minted:
        hard_case_buffer.expire(case_ids)
    return DesignerReport(len(clusters), minted, cost)
