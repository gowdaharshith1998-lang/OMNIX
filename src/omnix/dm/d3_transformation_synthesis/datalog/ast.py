"""Datalog AST dataclasses (frozen)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Tuple


@dataclass(frozen=True)
class Term:
    kind: Literal["var", "const"]
    value: Any  # str for var (name), Any for const

    def is_var(self) -> bool:
        return self.kind == "var"


@dataclass(frozen=True)
class Atom:
    predicate: str
    terms: Tuple[Term, ...]
    negated: bool = False

    @property
    def arity(self) -> int:
        return len(self.terms)


@dataclass(frozen=True)
class ArithConstraint:
    """A built-in body constraint like ``Y == Z * 2`` or ``X < 10``.

    ``lhs`` and ``rhs`` are either a variable name (str), a constant
    (int/float/str), or a tuple ``(left, op, right)`` for nested arithmetic.
    """

    lhs: Any
    op: str  # ==, !=, <, <=, >, >=
    rhs: Any


@dataclass(frozen=True)
class Aggregate:
    fn: str  # count, sum, min, max
    var: str  # variable to aggregate
    bind_to: str  # variable to bind the result to


@dataclass(frozen=True)
class Rule:
    head: Atom
    body: Tuple[Atom, ...]
    constraints: Tuple[ArithConstraint, ...] = ()
    aggregate: "Aggregate | None" = None


@dataclass(frozen=True)
class Program:
    rules: Tuple[Rule, ...]
    edb_predicates: frozenset = frozenset()


__all__ = ["Term", "Atom", "ArithConstraint", "Aggregate", "Rule", "Program"]
