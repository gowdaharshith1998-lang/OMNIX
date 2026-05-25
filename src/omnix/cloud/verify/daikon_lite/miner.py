"""Daikon-lite invariant miner."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any


@dataclass
class Snapshot:
    point: str       # "fn:entry" / "fn:exit"
    values: dict[str, Any]


@dataclass
class Invariant:
    point: str
    expression: str          # human-readable form
    kind: str
    args: tuple = ()
    confidence: float = 1.0

    def __hash__(self) -> int:
        return hash((self.point, self.expression))


@dataclass
class InvariantSet:
    by_point: dict[str, set[Invariant]] = field(default_factory=dict)

    def add(self, inv: Invariant) -> None:
        self.by_point.setdefault(inv.point, set()).add(inv)

    def union(self) -> set[Invariant]:
        out: set[Invariant] = set()
        for s in self.by_point.values():
            out |= s
        return out

    def __contains__(self, item: Invariant) -> bool:
        return item in self.by_point.get(item.point, set())


@dataclass
class ProgramPoint:
    """One execution-point sample set for a fn.

    Stored as parallel dicts of var-name -> list of values (one per observation).
    """
    name: str
    samples: list[Snapshot] = field(default_factory=list)


# ----------------------- tracer -----------------------

class Tracer:
    """Lightweight decorator-based tracer.

    @Tracer().trace("fn")
    def fn(x, y): ...
    Captures (x, y) at entry and (ret,) at exit.
    """

    def __init__(self) -> None:
        self.points: dict[str, ProgramPoint] = {}

    def trace(self, fn_name: str):
        def deco(fn: Callable):
            entry_name = f"{fn_name}:entry"
            exit_name = f"{fn_name}:exit"
            self.points.setdefault(entry_name, ProgramPoint(entry_name))
            self.points.setdefault(exit_name, ProgramPoint(exit_name))

            @wraps(fn)
            def wrap(*args, **kwargs):
                names = fn.__code__.co_varnames[: fn.__code__.co_argcount]
                values = dict(zip(names, args))
                values.update(kwargs)
                self.points[entry_name].samples.append(
                    Snapshot(point=entry_name, values=dict(values))
                )
                ret = fn(*args, **kwargs)
                self.points[exit_name].samples.append(
                    Snapshot(point=exit_name, values={**values, "_ret": ret})
                )
                return ret

            return wrap

        return deco


# ----------------------- mining -----------------------

def _numbers(seq: Iterable[Any]) -> list[float] | None:
    out: list[float] = []
    for v in seq:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        out.append(float(v))
    return out


def _mine_scalar(point: str, name: str, values: list[Any]) -> set[Invariant]:
    out: set[Invariant] = set()
    if not values:
        return out
    # constant
    if all(v == values[0] for v in values):
        out.add(Invariant(point, f"{name} == {values[0]!r}", "constant", (values[0],)))
        return out  # constants subsume the other unary forms

    nums = _numbers(values)
    if nums is None:
        return out
    if all(v != 0 for v in nums):
        out.add(Invariant(point, f"{name} != 0", "non-zero"))
    if all(v >= 0 for v in nums):
        out.add(Invariant(point, f"{name} >= 0", "non-negative"))
    if all(v <= 0 for v in nums):
        out.add(Invariant(point, f"{name} <= 0", "non-positive"))
    lo, hi = min(nums), max(nums)
    if hi - lo < 32 and all(float(int(v)) == v for v in nums):
        out.add(Invariant(point, f"{int(lo)} <= {name} <= {int(hi)}", "range", (int(lo), int(hi))))
    return out


def _mine_pair_linear(point: str, x_name: str, y_name: str,
                      xs: list[float], ys: list[float]) -> Invariant | None:
    """Detect ys = a*xs + b with very high confidence (no noise tolerance)."""
    if len(xs) < 2 or len(set(xs)) < 2:
        return None
    # Pick two anchor points with distinct xs so the slope is well-defined.
    x0 = xs[0]
    y0 = ys[0]
    x1 = y1 = None
    for xi, yi in zip(xs, ys):
        if xi != x0:
            x1, y1 = xi, yi
            break
    if x1 is None:
        return None
    a = (y1 - y0) / (x1 - x0)
    b = y0 - a * x0
    for x, y in zip(xs, ys):
        if abs(a * x + b - y) > 1e-9:
            return None
    if a == 1 and b == 0:
        return Invariant(point, f"{y_name} == {x_name}", "equal")
    sign = "+" if b >= 0 else "-"
    return Invariant(point, f"{y_name} == {a}*{x_name} {sign} {abs(b)}", "linear", (a, b))


def _mine_pair_ordering(point: str, x_name: str, y_name: str,
                        xs: list[float], ys: list[float]) -> set[Invariant]:
    out: set[Invariant] = set()
    if all(x < y for x, y in zip(xs, ys)):
        out.add(Invariant(point, f"{x_name} < {y_name}", "lt"))
    elif all(x <= y for x, y in zip(xs, ys)):
        out.add(Invariant(point, f"{x_name} <= {y_name}", "le"))
    if all(x > y for x, y in zip(xs, ys)):
        out.add(Invariant(point, f"{x_name} > {y_name}", "gt"))
    elif all(x >= y for x, y in zip(xs, ys)):
        out.add(Invariant(point, f"{x_name} >= {y_name}", "ge"))
    return out


def _mine_sequence(point: str, name: str, values: list[Any]) -> set[Invariant]:
    out: set[Invariant] = set()
    if not all(isinstance(v, (list, tuple)) for v in values):
        return out
    if all(len(v) > 0 for v in values):
        out.add(Invariant(point, f"len({name}) > 0", "non-empty"))
    if all(all(isinstance(x, (int, float)) and x > 0 for x in v) for v in values):
        out.add(Invariant(point, f"all({name}) > 0", "all-positive"))
    if all(list(v) == sorted(v) for v in values if v):
        out.add(Invariant(point, f"sorted({name})", "sorted"))
    return out


def mine(points: dict[str, ProgramPoint] | Tracer) -> InvariantSet:
    if isinstance(points, Tracer):
        points = points.points
    inv = InvariantSet()
    for pname, point in points.items():
        if not point.samples:
            continue
        # Collect parallel observation lists per variable name.
        per_var: dict[str, list[Any]] = {}
        for snap in point.samples:
            for k, v in snap.values.items():
                per_var.setdefault(k, []).append(v)

        # Scalar invariants
        for name, values in per_var.items():
            for inv_ in _mine_scalar(pname, name, values):
                inv.add(inv_)
            for inv_ in _mine_sequence(pname, name, values):
                inv.add(inv_)

        # Pair invariants over numeric pairs (consider both orderings for linear)
        numeric_vars = {k: _numbers(v) for k, v in per_var.items()}
        numeric_vars = {k: v for k, v in numeric_vars.items() if v is not None}
        names = sorted(numeric_vars)
        for i, x in enumerate(names):
            for y in names[i + 1 :]:
                xs, ys = numeric_vars[x], numeric_vars[y]
                if len(xs) != len(ys):
                    continue
                if (linear := _mine_pair_linear(pname, x, y, xs, ys)) is not None:
                    inv.add(linear)
                if (linear := _mine_pair_linear(pname, y, x, ys, xs)) is not None:
                    inv.add(linear)
                for inv_ in _mine_pair_ordering(pname, x, y, xs, ys):
                    inv.add(inv_)
    return inv


def compare(legacy: InvariantSet, candidate: InvariantSet) -> dict[str, list[Invariant]]:
    """Return the set of legacy invariants violated on the candidate, plus
    new/removed invariants between the two."""
    legacy_set = legacy.union()
    candidate_set = candidate.union()
    return {
        "violated": sorted(legacy_set - candidate_set, key=lambda i: (i.point, i.expression)),
        "introduced": sorted(candidate_set - legacy_set, key=lambda i: (i.point, i.expression)),
        "agreed": sorted(legacy_set & candidate_set, key=lambda i: (i.point, i.expression)),
    }
