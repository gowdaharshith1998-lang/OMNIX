"""Singleton Hypothesis strategies for hot verify paths (Layer 5, R2.1.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import hypothesis.strategies as st

from hypothesis.strategies._internal.lazy import unwrap_strategies


def _fresh_broad_one_of() -> Any:
    return st.one_of(st.integers(), st.text(), st.none(), st.booleans())


@dataclass(frozen=True)
class InlinedStrategyBundle:
    """Pair used by equivalence tests: factory-built *vs* module singleton."""

    name: str
    fresh_factory: Callable[[], Any]
    inlined_singleton: Any

    @property
    def original(self) -> Any:
        return self.fresh_factory()

    @property
    def inlined(self) -> Any:
        return self.inlined_singleton


_INT_S = st.integers()
_TXT_S = st.text()
_BOOL_S = st.booleans()
_NONE_S = st.none()
_BROAD_S = st.one_of(_INT_S, _TXT_S, _NONE_S, _BOOL_S)

INLINED_REGISTRY: dict[str, InlinedStrategyBundle] = {
    "omnix_inline.integers": InlinedStrategyBundle(
        "omnix_inline.integers", lambda: st.integers(), _INT_S
    ),
    "omnix_inline.text": InlinedStrategyBundle(
        "omnix_inline.text", lambda: st.text(), _TXT_S
    ),
    "omnix_inline.booleans": InlinedStrategyBundle(
        "omnix_inline.booleans", lambda: st.booleans(), _BOOL_S
    ),
    "omnix_inline.none": InlinedStrategyBundle(
        "omnix_inline.none", lambda: st.none(), _NONE_S
    ),
    "omnix_inline.broad_one_of": InlinedStrategyBundle(
        "omnix_inline.broad_one_of", _fresh_broad_one_of, _BROAD_S
    ),
}


def default_text_repr() -> str:
    return repr(unwrap_strategies(_TXT_S))


def get_inlined_strategy(name: str) -> InlinedStrategyBundle | None:
    return INLINED_REGISTRY.get(name)
