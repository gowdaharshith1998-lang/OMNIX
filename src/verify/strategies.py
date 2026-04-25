"""Build Hypothesis strategies from type hints + caller-shape + boundaries."""

from __future__ import annotations

import re
from typing import Any

import hypothesis.strategies as st

# Exposed for tests (alias)
hypothesis_strategies = st

_BROAD = (st.integers(), st.text(), st.none(), st.booleans())


def _list_inner(ann: str) -> str:
    ann = re.sub(r"^(typing\.)?List\[(.*)\]\s*$", r"\1", ann)
    m = re.match(
        r"^(list|List)\[([^]]*)\]\s*$", ann.strip()
    ) or re.match(
        r"^typing\.List\[(.*)\]\s*$", ann
    )
    if m and len(m.groups()) >= 1:
        return m.group(m.lastindex) if m.lastindex else m.group(1)  # type: ignore[operator]
    if ann.startswith("list[") and ann.endswith("]"):
        return ann[5:-1].strip()
    if "List[" in ann:
        s = ann.index("List[")
        e = ann.rindex("]")
        return ann[s + 5 : e]
    if "[" in ann and ann.endswith("]"):
        return ann[ann.index("[") + 1 : ann.rindex("]")].strip()
    return "str"


def strategy_from_type_hint(h: str | None) -> Any:
    if not h or not h.strip():
        return st.one_of(*_BROAD)  # type: ignore[call-overload,operator]
    t = h.strip()
    t = t.replace("typing.", "")
    if t == "int":
        return st.integers()
    if t == "str":
        return st.text()
    if t == "bool":
        return st.booleans()
    if t == "float":
        return st.floats(allow_nan=False, allow_infinity=False)
    if t == "bytes":
        return st.binary()
    if t.startswith("Union[") and t.endswith("]"):
        inner = t[6:-1]
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        subs = [strategy_from_type_hint(p) for p in parts]
        return st.one_of(*subs) if subs else st.one_of(*_BROAD)  # type: ignore[operator, arg-type]
    if "|" in t:
        parts = [p.strip() for p in re.split(r"\s*\|\s*", t) if p.strip()]
        subs2 = [strategy_from_type_hint(p) for p in parts if p != "None" and p != "type(None)"]  # noqa: E501
        if "None" in t or "type(None)" in t or any(p in ("None",) for p in parts):
            subs2.append(st.none())  # type: ignore[operator, arg-type]
        if subs2:
            return st.one_of(*subs2)  # type: ignore[operator, arg-type]
    if re.match(r"^list\[(.*)\]$", t, re.IGNORECASE) or t.startswith("List[") or (
        t
        and (t[0:4] == "list" or t[:1] in ("L",))
    ):
        ito = t[t.index("[") + 1 : t.rindex("]")].strip()
        inner_st = _elem(ito)
        return st.lists(inner_st, max_size=5)
    if t.startswith("Tuple[") or t.startswith("tuple["):
        inners = t[t.index("[") + 1 : t.rindex("]")].split(",")
        sgs: list = []
        for p in inners:
            sgs.append(_elem(p.strip().split("=")[0].strip() if p else "str"))  # type: ignore[arg-type, assignment]
        if not sgs:
            return st.tuples(st.text(), st.text())  # type: ignore[call-arg]
        if len(sgs) == 1:
            return st.tuples(sgs[0])
        return st.tuples(*sgs[:2] if len(sgs) > 1 else sgs)  # type: ignore[call-overload, arg-type]
    if t.startswith("Dict[") or t.startswith("dict[") or t.startswith("dict[") or t.startswith("Dict["):
        return st.dictionaries(
            st.text(), st.integers() if "int" in t else st.text(), max_size=2
        )
    return st.one_of(*_BROAD)  # type: ignore[operator, call-overload]


def _elem(name: str) -> Any:
    s = (name or "str").strip()
    s = s.replace("typing.", "")
    if s in ("int", "Integer"):
        return st.integers()
    if s in ("str", "Text"):
        return st.text()
    if s in ("bool", "Boolean"):
        return st.booleans()
    if s in ("float", "Float", "Number"):
        return st.floats(allow_nan=False, allow_infinity=False)  # type: ignore[operator, arg-type, call-arg]
    return st.text()  # type: ignore[operator]


def _strategies_from_caller_types(raw: dict[str, int]) -> list:
    order = sorted(raw.items(), key=lambda kv: -kv[1])
    out: list = []
    seen: set[str] = set()
    for k, _c in order:
        kk = (k or "")
        if kk == "int" or (kk and kk.lower() == "int") or (kk and "int" in kk.lower() and "point" not in kk):
            if "i" not in seen:
                seen.add("i")
                out.append(st.integers())  # type: ignore[operator, arg-type]
        elif k == "str" or (kk and "str" in kk.lower() and "list" not in kk.lower()):  # noqa: E501
            if "s" not in seen:
                seen.add("s")
                out.append(st.text())  # type: ignore[operator, arg-type]
        elif "None" in (k or "") or (kk and "none" in kk.lower()):  # noqa: E501
            if "n" not in seen:
                seen.add("n")
                out.append(st.none())  # type: ignore[operator, arg-type]
    return out or [st.integers(), st.text(), st.booleans(), st.none()]  # type: ignore[operator, list-item]


def strategy_for_param(
    param_index: int,
    type_hint: str | None,
    caller_by_pos: dict[int, dict[str, int]],
    boundary_vals: list[Any] | None,
) -> Any:
    boundary_vals = list(boundary_vals) if boundary_vals else []
    raw: dict[str, int] = dict(caller_by_pos.get(param_index) or {})

    if type_hint and type_hint.strip() and "Any" not in type_hint:
        try:
            st_base: Any = strategy_from_type_hint(type_hint)
        except (Exception,):
            st_base = st.one_of(*_BROAD)  # type: ignore[call-overload, operator]
    elif raw:
        parts = _strategies_from_caller_types(raw)
        st_base = parts[0] if len(parts) == 1 else st.one_of(*parts)  # type: ignore[operator, arg-type, assignment]
    else:
        st_base = st.one_of(*_BROAD)  # type: ignore[operator, call-overload]
    bset: list = []
    for x in boundary_vals:
        if all(v != x for v in bset):
            bset.append(x)
    if bset:
        j = [st.just(x) for x in bset]
        return st.one_of(*(j + [st_base]))  # type: ignore[return-value, operator, arg-type, call-overload]
    return st_base
