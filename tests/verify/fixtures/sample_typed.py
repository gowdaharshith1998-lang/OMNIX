"""Fixture: fully type-hinted functions for PBT tests."""

from __future__ import annotations

from typing import List, Tuple


def add(a: int, b: int) -> int:
    return a + b


def join_words(parts: List[str], sep: str) -> str:
    return sep.join(parts)


def parse_pair(s: str) -> Tuple[str, str]:
    a, b = s.split(":", 1)
    return (a, b)
