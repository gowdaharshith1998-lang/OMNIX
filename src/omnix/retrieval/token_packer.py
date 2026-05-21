"""Pack retrieved graph context into a token budget."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackedBundle:
    included: list[tuple[str, str]]
    excluded: list[tuple[str, str]]
    estimated_tokens: int
    retrieval_modes: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def node_ids(self) -> list[str]:
        return [node_id for node_id, _content in self.included]

    @property
    def content(self) -> str:
        return "\n\n".join(f"# {node_id}\n{text}" for node_id, text in self.included)


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def pack_into_budget(
    nodes_with_content: list[tuple[str, str]],
    budget_tokens: int,
    safety_margin: float = 0.10,
    *,
    scores: dict[str, float] | None = None,
    retrieval_modes: dict[str, int] | None = None,
) -> PackedBundle:
    ceiling = int(max(0, budget_tokens) * (1.0 - safety_margin))
    included: list[tuple[str, str]] = []
    excluded: list[tuple[str, str]] = []
    used = 0
    for node_id, content in nodes_with_content:
        cost = estimate_tokens(content)
        if included and used + cost > ceiling:
            excluded.append((node_id, content))
            continue
        if not included and cost > ceiling:
            included.append((node_id, content[: max(1, ceiling * 4)]))
            used = ceiling
            continue
        included.append((node_id, content))
        used += cost
    return PackedBundle(
        included,
        excluded,
        used,
        retrieval_modes=dict(retrieval_modes or {}),
        scores=dict(scores or {}),
    )
