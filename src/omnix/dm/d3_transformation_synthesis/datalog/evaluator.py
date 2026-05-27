"""Semi-naïve Datalog evaluator over a stratified program.

Maintains the IDB as ``{predicate: set[tuple]}``. At each stratum, iterates
until no new facts are derived. Built-in arithmetic + comparison constraints
are evaluated against current bindings.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .ast import Aggregate, ArithConstraint, Atom, Program, Rule, Term
from .parser import DatalogSyntaxError, parse_program
from .stratification import StratificationError, stratify


class DatalogTimeout(RuntimeError):
    """Raised when fixpoint iteration exceeds the wallclock budget."""


def evaluate(
    program: "Program | str",
    edb: Dict[str, Iterable[Tuple]],
    target: str,
    timeout_ms: int = 10_000,
) -> Tuple[Tuple, ...]:
    """Evaluate ``program`` over ``edb`` and return the derived tuples for
    ``target``. ``program`` may be a parsed :class:`Program` or raw Datalog
    source. Raises :class:`DatalogTimeout` on wallclock overrun.
    """
    if isinstance(program, str):
        program = parse_program(program)
    rule_strata = stratify(program)

    facts: Dict[str, Set[Tuple]] = {p: set(map(tuple, t)) for p, t in edb.items()}
    deadline = time.monotonic() + timeout_ms / 1000.0
    max_stratum = max(rule_strata) if rule_strata else 0
    for stratum in range(max_stratum + 1):
        rules_at = [r for r, s in zip(program.rules, rule_strata) if s == stratum]
        changed = True
        while changed:
            if time.monotonic() > deadline:
                raise DatalogTimeout(
                    f"fixpoint not reached within {timeout_ms}ms (stratum {stratum})"
                )
            changed = False
            for rule in rules_at:
                derived = _apply_rule(rule, facts)
                target_set = facts.setdefault(rule.head.predicate, set())
                before = len(target_set)
                target_set.update(derived)
                if len(target_set) != before:
                    changed = True
    return tuple(sorted(facts.get(target, set())))


def _apply_rule(rule: Rule, facts: Dict[str, Set[Tuple]]) -> Set[Tuple]:
    if rule.aggregate is not None:
        return _apply_aggregate_rule(rule, facts)
    return _derive_basic(rule, facts)


def _derive_basic(rule: Rule, facts: Dict[str, Set[Tuple]]) -> Set[Tuple]:
    derived: Set[Tuple] = set()
    for binding in _enumerate_bindings(rule.body, facts):
        extended = _apply_binding_constraints(rule.constraints, binding)
        if extended is None:
            continue
        if not _eval_filter_constraints(rule.constraints, extended):
            continue
        head_tuple = tuple(_resolve_term(t, extended) for t in rule.head.terms)
        derived.add(head_tuple)
    return derived


def _apply_aggregate_rule(rule: Rule, facts: Dict[str, Set[Tuple]]) -> Set[Tuple]:
    agg = rule.aggregate
    assert agg is not None
    # Group bindings by every head var except agg.bind_to. For each group,
    # compute aggregate over agg.var.
    head_vars = [t for t in rule.head.terms if t.is_var()]
    group_keys = tuple(v.value for v in head_vars if v.value != agg.bind_to)
    groups: Dict[Tuple, List[Any]] = {}
    for binding in _enumerate_bindings(rule.body, facts):
        if not _eval_constraints(rule.constraints, binding):
            continue
        key = tuple(binding.get(k) for k in group_keys)
        groups.setdefault(key, []).append(binding.get(agg.var))
    derived: Set[Tuple] = set()
    for key, values in groups.items():
        agg_value = _compute_agg(agg.fn, values)
        binding = dict(zip(group_keys, key))
        binding[agg.bind_to] = agg_value
        head_tuple = tuple(_resolve_term(t, binding) for t in rule.head.terms)
        derived.add(head_tuple)
    if not groups:
        # empty body → produce one row with identity for the aggregate if the
        # head has no group vars.
        if not group_keys:
            agg_value = _compute_agg(agg.fn, [])
            binding = {agg.bind_to: agg_value}
            head_tuple = tuple(_resolve_term(t, binding) for t in rule.head.terms)
            derived.add(head_tuple)
    return derived


def _compute_agg(fn: str, values: List[Any]) -> Any:
    if fn == "count":
        return len(values)
    if fn == "sum":
        return sum(values) if values else 0
    if fn == "min":
        return min(values) if values else None
    if fn == "max":
        return max(values) if values else None
    raise DatalogSyntaxError(f"unknown aggregate fn {fn!r}")


def _enumerate_bindings(
    body: Tuple[Atom, ...],
    facts: Dict[str, Set[Tuple]],
) -> List[Dict[str, Any]]:
    """Cartesian join over body atoms, threading a single binding dict."""
    pos_atoms = [a for a in body if not a.negated]
    neg_atoms = [a for a in body if a.negated]

    bindings: List[Dict[str, Any]] = [{}]
    for atom in pos_atoms:
        next_bindings: List[Dict[str, Any]] = []
        for b in bindings:
            tuples = facts.get(atom.predicate, set())
            for t in tuples:
                merged = _unify(atom.terms, t, b)
                if merged is not None:
                    next_bindings.append(merged)
        bindings = next_bindings
    # Negation: keep only bindings where the negated atom has NO matching fact.
    for atom in neg_atoms:
        bindings = [
            b
            for b in bindings
            if not any(
                _unify(atom.terms, t, b) is not None
                for t in facts.get(atom.predicate, set())
            )
        ]
    return bindings


def _unify(
    terms: Tuple[Term, ...],
    tup: Tuple,
    binding: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if len(terms) != len(tup):
        return None
    new_binding = dict(binding)
    for t, val in zip(terms, tup):
        if t.is_var():
            if t.value in new_binding:
                if new_binding[t.value] != val:
                    return None
            else:
                new_binding[t.value] = val
        else:
            if t.value != val:
                return None
    return new_binding


def _resolve_term(t: Term, binding: Dict[str, Any]) -> Any:
    if t.is_var():
        if t.value not in binding:
            raise DatalogSyntaxError(
                f"unbound head variable {t.value!r} during evaluation"
            )
        return binding[t.value]
    return t.value


def _eval_constraints(
    constraints: Tuple[ArithConstraint, ...],
    binding: Dict[str, Any],
) -> bool:
    for c in constraints:
        lhs = _eval_expr(c.lhs, binding)
        rhs = _eval_expr(c.rhs, binding)
        if not _cmp(lhs, c.op, rhs):
            return False
    return True


def _apply_binding_constraints(
    constraints: Tuple[ArithConstraint, ...],
    binding: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Extend ``binding`` by evaluating ``Var == expr`` constraints where one
    side is an unbound var and the other side can be computed from the current
    binding. Returns the extended binding or ``None`` if any constraint cannot
    be satisfied during binding (no progress + still unbound).
    """
    out = dict(binding)
    pending = list(constraints)
    # Fixed-point: iterate until no more bindings can be produced.
    changed = True
    while changed:
        changed = False
        for c in pending:
            if c.op != "==":
                continue
            if _is_unbound_var(c.lhs, out) and _is_computable(c.rhs, out):
                out[c.lhs[1]] = _eval_expr(c.rhs, out)
                changed = True
            elif _is_unbound_var(c.rhs, out) and _is_computable(c.lhs, out):
                out[c.rhs[1]] = _eval_expr(c.lhs, out)
                changed = True
    return out


def _eval_filter_constraints(
    constraints: Tuple[ArithConstraint, ...],
    binding: Dict[str, Any],
) -> bool:
    for c in constraints:
        # If both sides are computable, treat as filter; otherwise it was a
        # binding constraint already processed.
        if _is_computable(c.lhs, binding) and _is_computable(c.rhs, binding):
            lhs = _eval_expr(c.lhs, binding)
            rhs = _eval_expr(c.rhs, binding)
            if not _cmp(lhs, c.op, rhs):
                return False
    return True


def _is_unbound_var(node: Any, binding: Dict[str, Any]) -> bool:
    if isinstance(node, tuple) and len(node) == 2 and node[0] == "var":
        return node[1] not in binding
    return False


def _is_computable(node: Any, binding: Dict[str, Any]) -> bool:
    if isinstance(node, tuple) and len(node) == 2 and node[0] == "var":
        return node[1] in binding
    if isinstance(node, tuple) and len(node) == 3 and isinstance(node[1], str):
        return _is_computable(node[0], binding) and _is_computable(node[2], binding)
    return True  # numeric / string literal


def _eval_expr(node: Any, binding: Dict[str, Any]) -> Any:
    if isinstance(node, tuple) and len(node) == 3 and isinstance(node[1], str):
        left = _eval_expr(node[0], binding)
        right = _eval_expr(node[2], binding)
        op = node[1]
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right
        if op == "%":
            return left % right
        raise DatalogSyntaxError(f"unknown arithmetic op {op!r}")
    if isinstance(node, tuple) and len(node) == 2 and node[0] == "var":
        name = node[1]
        if name not in binding:
            raise DatalogSyntaxError(f"unbound var {name!r} in constraint")
        return binding[name]
    return node


def _cmp(a: Any, op: str, b: Any) -> bool:
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    raise DatalogSyntaxError(f"unknown comparison op {op!r}")


__all__ = ["evaluate", "DatalogTimeout", "DatalogSyntaxError", "StratificationError"]
