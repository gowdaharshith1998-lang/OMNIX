"""Pure-Python semi-naïve Datalog evaluator.

Replaces unmaintained ``pyDatalog`` (last release Nov 2022, CPython 3.4 era).
Supports stratified Datalog with negation-as-failure, built-in comparison +
arithmetic predicates, and aggregation (count/sum/min/max). Termination is
guaranteed by stratification check at rule-load time.
"""

from __future__ import annotations

from .ast import Atom, Program, Rule, Term
from .evaluator import (
    DatalogSyntaxError,
    DatalogTimeout,
    StratificationError,
    evaluate,
)
from .parser import parse_program
from .stratification import stratify

__all__ = [
    "Atom",
    "Program",
    "Rule",
    "Term",
    "DatalogSyntaxError",
    "DatalogTimeout",
    "StratificationError",
    "evaluate",
    "parse_program",
    "stratify",
]
