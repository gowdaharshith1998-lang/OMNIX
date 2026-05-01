"""Layer 5: direct sampling equivalents for hot Hypothesis paths (R7 / Fail Faster style)."""

from __future__ import annotations

import logging
import os
import random
from typing import Any

from hypothesis.strategies._internal.lazy import unwrap_strategies
from hypothesis.strategies._internal.misc import BooleansStrategy, JustStrategy
from hypothesis.strategies._internal.numbers import IntegersStrategy
from hypothesis.strategies._internal.strategies import OneOfStrategy
from hypothesis.strategies._internal.strings import TextStrategy

from scan.turboscan.inlined_generators import (
    _BOOL_S,
    _BROAD_S,
    _INT_S,
    _NONE_S,
    _TXT_S,
    default_text_repr,
    get_inlined_strategy,
)

_LOG = logging.getLogger("omnix.scan.turboscan.inliner")


def inlined_int_pair(seed: int) -> tuple[int, int]:
    """Bypass combinator overhead: two independent uniform ints in ``[0, 100]``."""
    rng = random.Random(seed)
    return (rng.randint(0, 100), rng.randint(0, 100))


def monadic_reference_pair(seed: int) -> tuple[int, int]:
    """Semantic reference — same RNG draws as :func:`inlined_int_pair`."""
    rng = random.Random(seed)
    return (rng.randint(0, 100), rng.randint(0, 100))


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes")


def _is_verify_broad_one_of(u: OneOfStrategy) -> bool:
    orig = u.original_strategies
    if len(orig) != 4:
        return False
    kinds: list[str] = []
    for s in orig:
        w = unwrap_strategies(s)
        kinds.append(type(w).__name__)
    return kinds == [
        "IntegersStrategy",
        "TextStrategy",
        "JustStrategy",
        "BooleansStrategy",
    ]


def _plain_unbounded_integers(u: IntegersStrategy) -> bool:
    return u.start is None and u.end is None


def _default_utf8_text(u: TextStrategy) -> bool:
    return repr(u) == default_text_repr()


def maybe_substitute_hypothesis_strategy(strategy: Any) -> Any:
    """Swap hot strategies for module singletons when inline env is enabled (R2.1.4)."""
    if not _truthy_env("OMNIX_TURBOSCAN_INLINE"):
        return strategy
    u = unwrap_strategies(strategy)
    if isinstance(u, IntegersStrategy) and _plain_unbounded_integers(u):
        return _INT_S
    if isinstance(u, TextStrategy) and _default_utf8_text(u):
        return _TXT_S
    if isinstance(u, BooleansStrategy):
        return _BOOL_S
    if isinstance(u, JustStrategy) and u.value is None:
        return _NONE_S
    if isinstance(u, OneOfStrategy) and _is_verify_broad_one_of(u):
        return _BROAD_S
    return strategy


__all__ = [
    "get_inlined_strategy",
    "inlined_int_pair",
    "maybe_substitute_hypothesis_strategy",
    "monadic_reference_pair",
]
