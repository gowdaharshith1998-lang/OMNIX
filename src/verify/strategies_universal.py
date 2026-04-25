"""Layer 6: synthesize PBT / fuzz value hints from universal parse metadata (no Hypothesis in hot path)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Boundary presets for fuzzy testing (portable, JSON-friendly).
def boundary_int_values() -> list[int]:
    return [0, -1, 1, 2**30 - 1, -(2**30)]


def boundary_str_values() -> list[str]:
    return ["", "a" * 1024, "\n\t", "\0"]


@dataclass(frozen=True)
class StrategySynthesis:
    """Synthesis for one callable target; ``mode`` steers the runner choice."""

    mode: str
    """``native_rust`` | ``native_go`` | ``llm`` | ``dynamic``"""

    param_types: tuple[str, ...] = ()
    """Best-effort type names per position."""

    native_hint: str | None = None
    """Fuzzer family hint: ``cargo_fuzz`` | ``go_fuzz`` | None."""

    boundary_values: list[Any] = field(default_factory=list)
    """Concrete samples (ints, strs, lists) for the subprocess+LLM floor."""


def _parse_rust_params(between_parens: str) -> list[str]:
    if not between_parens.strip():
        return []
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in between_parens:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            t = "".join(cur).strip()
            if t:
                parts.append(t)
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def synthesize_from_rust_signature(line: str) -> StrategySynthesis:
    """
    Parse ``fn name(a: T, b: U)`` / ``fn name``, best-effort from a single line or snippet.
    """
    t = (line or "").strip()
    m = re.search(r"fn\s+\w+\s*\(([^)]*)\)", t)
    inner = m.group(1) if m else ""
    pchunks = _parse_rust_params(inner) if m else []
    ptypes: list[str] = []
    for c in pchunks:
        c = c.strip()
        if c.startswith("self") or c.startswith("&mut self") or c.startswith("&self"):
            continue
        mm = re.match(r"^(?:\w+|\w+\s*:\s*:\s*[\w<>,\s]+)?\s*:\s*([\w&'\[\]<> \]]+?)(?:\s*=\s*[^,]+)?$", c)
        if not mm:
            m2 = re.split(r":", c, maxsplit=1)
            ptypes.append(m2[1].strip() if len(m2) == 2 else c)
        else:
            ptypes.append(re.sub(r"^\s*&'?\s*\w*\s*", "", mm.group(1)).strip())
    ptypes = [re.sub(r"\s+", " ", p) for p in ptypes if p]
    bounds: list[Any] = list(boundary_int_values())
    for pt in ptypes:
        ptl = pt.lower()
        if "i32" in ptl or "i64" in ptl or "u32" in ptl or "usize" in ptl or "i128" in ptl:
            bounds.extend(boundary_int_values())
        elif "str" in ptl or "string" in ptl or "osstring" in ptl:
            bounds.extend(boundary_str_values())
    return StrategySynthesis(
        mode="native_rust",
        param_types=tuple(ptypes),
        native_hint="cargo_fuzz",
        boundary_values=bounds,
    )


def _parse_go_params(s: str) -> list[str]:
    """``name1 type1, name2 type2`` (best-effort)."""
    t = s.strip()
    if not t:
        return []
    segs: list[str] = []
    depth = 0
    cur2: list[str] = []
    for ch2 in t:
        if ch2 in "<[(":
            depth += 1
        elif ch2 in ">])":
            depth = max(0, depth - 1)
        if ch2 == "," and depth == 0:
            segs.append("".join(cur2).strip())
            cur2 = []
            continue
        cur2.append(ch2)
    if cur2:
        segs.append("".join(cur2).strip())
    out: list[str] = []
    for seg2 in segs:
        w = seg2.split()
        if len(w) >= 2 and not seg2.startswith("..."):
            out.append(" ".join(w[1:]))
    return out


def synthesize_from_go_signature(line: str) -> StrategySynthesis:
    t = (line or "").replace("\n", " ").strip()
    m2 = re.search(
        r"func\s+\([^)]*?\)\s+\w+\s*\(([^)]*)\)",
        t,
    ) or re.search(
        r"func\s+\w+\s*\(([^)]*)\)",
        t,
    )
    inner = m2.group(1) if m2 else ""
    ptypes: list[str] = _parse_go_params(inner) or []
    if not ptypes and m2 and inner:
        ptypes = [p.strip() for p in re.split(r",\s*", inner) if p.strip() and p.strip() != "ctx context.Context" ]
    ptypes2 = [
        re.sub(r"\A\*", "", p).strip()
        for p in ptypes
        if p
        and "context.context" not in p.lower()
        and not p.lower().strip().startswith("context.")
    ]
    b: list[Any] = []
    for pt in ptypes2:
        ptl = (pt or "").lower().strip()
        intish = ptl in (
            "int",
            "int8",
            "int16",
            "int32",
            "int64",
            "int128",
            "uint",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
            "uint128",
            "uintptr",
        ) or ptl == "rune"
        if intish and "string" not in ptl and "[]byte" not in ptl:
            b.extend(boundary_int_values())
        elif "string" in ptl or "[]byte" in ptl:
            b.extend(boundary_str_values() + [b""])
        elif ptl == "rune":
            b.extend(boundary_int_values()[:2])
    if not ptypes2:
        return StrategySynthesis(
            mode="dynamic",
            param_types=(),
            native_hint="go_fuzz",
            boundary_values=b,
        )
    return StrategySynthesis(
        mode="native_go",
        param_types=tuple(ptypes2),
        native_hint="go_fuzz",
        boundary_values=b or [0, 1, ""],
    )


def synthesize_dynamic_for_llm(_reason: str = "unknown_types") -> StrategySynthesis:
    """Dynamic or missing type info: LLM+subprocess path must supply vectors."""
    return StrategySynthesis(
        mode="llm",
        param_types=(),
        native_hint=None,
        boundary_values=[*boundary_int_values(), *boundary_str_values()[:1]],
    )


def apply_node_metadata(
    param_lines: list[str] | None,
) -> StrategySynthesis:
    """
    If parser attached ``(name: type)``-like strings, map heuristics; else LLM.
    """
    if not param_lines or all(not p.strip() for p in param_lines):
        return synthesize_dynamic_for_llm("no_params")
    joined = " ".join(p.strip() for p in param_lines)
    if "fn " in joined or any(c in joined for c in ("&self", "impl ", "->")):
        return synthesize_from_rust_signature(joined)
    if re.search(r"func\s+", joined) or re.search(r"\bfunc\(", joined):
        return synthesize_from_go_signature(joined)
    if re.search(r"\*any|interface\{\}|any\b", joined, re.I) or re.search(
        r"\bDynamic\b|reflect\.", joined
    ):
        return synthesize_dynamic_for_llm("dynamic_typing")
    if not re.search(r"[:=]", joined):
        return synthesize_dynamic_for_llm("missing_types")
    return synthesize_dynamic_for_llm("fallback")
