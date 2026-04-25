"""Fixture: no type hints (caller-shape inference will drive strategies)."""

from __future__ import annotations


def merge(a, b, c=10):
    """Default c=10 is recorded but not used as a bound for generation."""
    return a + b + c
