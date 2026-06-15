"""
Heuristic graph quality score (0.0–1.0) for LLM fallback gating (Layer 3 uses thresholds).

**v1 (legacy):** :func:`compute_score` uses one language-agnostic :class:`QualityInputs`
formula (thresholds + line-density). Evolution receipts with ``schema_version`` 1 or
2 used this; schema **3** sets ``quality_formula_version`` to 1 (legacy) or
2 (per-grammar) (see ``docs/PHASES.md``).

**v2:** :func:`compute_score_v2` consults ``src/omnix/parser/quality_profiles/``; when no
profile match exists, :func:`load_profile` falls back to ``generic.json``; if that
is also missing, :func:`compute_score` is used.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from omnix.parser.quality_profiles import (
    QualityProfile,
    load_custom_score,
    load_profile,
)


@dataclass(frozen=True)
class QualityInputs:
    n_functions: int
    n_classes: int
    n_imports: int
    n_call_edges: int
    n_lines: int
    function_class_names: tuple[str, ...]
    # Per-grammar / syntactic add-ons (Phase 3b+); all default to empty / zero.
    n_interface_declaration: int = 0
    n_type_alias_declaration: int = 0
    n_enum_declaration: int = 0
    n_arrow_function: int = 0
    n_function_declaration: int = 0
    n_method_declaration: int = 0
    n_struct_type: int = 0
    n_interface_type: int = 0
    n_import_declaration: int = 0
    n_function_item: int = 0
    n_impl_item: int = 0
    n_struct_item: int = 0
    n_trait_item: int = 0
    n_use_declaration: int = 0
    type_decl_names: tuple[str, ...] = field(default_factory=tuple)


def _name_looks_synthetic(n: str) -> bool:
    t = n.strip()
    if not t:
        return True
    if t.startswith("anonymous_"):
        return True
    if re.match(r"^node_\d+$", t):
        return True
    return False


def _n_non_synthetic_names(i: QualityInputs) -> int:
    a = [x for x in i.function_class_names if x and not _name_looks_synthetic(x)]
    b = [x for x in i.type_decl_names if x and not _name_looks_synthetic(x)]
    return len(a) + len(b)


def _line_density(i: QualityInputs) -> float:
    if i.n_lines <= 0 or i.n_functions <= 0:
        return 0.0
    return i.n_functions / i.n_lines


def _stat_for_profile_key(i: QualityInputs, key: str) -> int | float:
    k = key
    if k == "function_or_method":
        return int(i.n_functions)
    if k in ("function_declaration", "function_count"):
        return int(max(i.n_function_declaration, i.n_functions))
    if k in ("class_declaration", "class_count"):
        return int(i.n_classes)
    if k == "struct_type":
        return int(i.n_struct_type)
    if k == "struct_item":
        return int(i.n_struct_item)
    if k == "interface_type":
        return int(i.n_interface_type)
    if k == "method_declaration":
        return int(i.n_method_declaration)
    if k in ("import_statement", "import_count"):
        return int(i.n_imports)
    if k == "import_or_use":
        return int(max(i.n_imports, i.n_use_declaration))
    if k == "import_declaration":
        return int(
            i.n_import_declaration
            if i.n_import_declaration > 0
            else i.n_imports
        )
    if k == "use_declaration":
        return int(max(i.n_use_declaration, i.n_imports))
    if k in ("call_edge", "call_edge_count"):
        return int(i.n_call_edges)
    if k in ("non_synthetic_names", "non_synthetic_name_count"):
        return int(_n_non_synthetic_names(i))
    if k == "line_density":
        return float(_line_density(i))
    if k == "function_item":
        return int(i.n_function_item)
    if k == "impl_item":
        return int(i.n_impl_item)
    if k == "trait_item":
        return int(i.n_trait_item)
    if k == "interface_declaration":
        return int(i.n_interface_declaration)
    if k == "type_alias_declaration":
        return int(i.n_type_alias_declaration)
    if k == "enum_declaration":
        return int(i.n_enum_declaration)
    if k == "arrow_function":
        return int(i.n_arrow_function)
    return 0


def _line_density_bucket_v1(i: QualityInputs) -> bool:
    """Matches :func:`compute_score` +0.1 line-density test."""
    if i.n_lines <= 10 or i.n_lines <= 0 or i.n_functions <= 0:
        return False
    return (i.n_functions / i.n_lines) > 0.05


def _bucket_satisfied(
    key: str, val: int | float, profile: QualityProfile, i: QualityInputs
) -> bool:
    if key == "line_density":
        if key in profile.required_minimums:
            need = int(profile.required_minimums[key])
            if need > 0:
                return _line_density_bucket_v1(i) and float(val) >= need
        return _line_density_bucket_v1(i)
    if key in profile.required_minimums:
        need = int(profile.required_minimums[key])
        return val >= need
    if isinstance(val, float):
        return val > 0.0
    return int(val) >= 1


def _apply_weighted_sum(i: QualityInputs, profile: QualityProfile) -> float:
    s = 0.0
    for wkey, w in profile.weights.items():
        v = _stat_for_profile_key(i, wkey)
        if _bucket_satisfied(wkey, v, profile, i):
            s += w
    return round(min(1.0, s), 4)


def _quality_inputs_to_stats_dict(i: QualityInputs) -> dict[str, Any]:
    """Bridge for ``custom_python`` profiles (``def score(stats: dict) -> float``)."""
    d: dict[str, Any] = dict(asdict(i))
    d["function_class_names"] = list(i.function_class_names)
    d["type_decl_names"] = list(i.type_decl_names)
    d["n_non_synthetic_names"] = _n_non_synthetic_names(i)
    d["line_density"] = _line_density(i)
    return d


def _apply_python_profile(i: QualityInputs, profile: QualityProfile) -> float:
    p = profile.python_module
    if not p:
        raise ValueError("custom_python profile missing python_module path")
    fn = load_custom_score(p)
    return float(fn(_quality_inputs_to_stats_dict(i)))


def quality_inputs_from_parsed_stats(stats: dict[str, Any]) -> QualityInputs:
    """Build :class:`QualityInputs` from :func:`parse_stats_for_universal_ingest` output."""
    td = stats.get("type_decl_names")
    if not isinstance(td, (tuple, list)):
        tdt: tuple[str, ...] = ()
    else:
        tdt = tuple(str(x) for x in td)
    return QualityInputs(
        n_functions=int(stats.get("n_functions", 0) or 0),
        n_classes=int(stats.get("n_classes", 0) or 0),
        n_imports=int(stats.get("n_imports", 0) or 0),
        n_call_edges=int(stats.get("n_call_edges", 0) or 0),
        n_lines=int(stats.get("n_lines", 0) or 0),
        function_class_names=tuple(stats.get("function_class_names", ()) or ()),
        n_interface_declaration=int(stats.get("n_interface_declaration", 0) or 0),
        n_type_alias_declaration=int(stats.get("n_type_alias_declaration", 0) or 0),
        n_enum_declaration=int(stats.get("n_enum_declaration", 0) or 0),
        n_arrow_function=int(stats.get("n_arrow_function", 0) or 0),
        n_function_declaration=int(stats.get("n_function_declaration", 0) or 0),
        n_method_declaration=int(stats.get("n_method_declaration", 0) or 0),
        n_struct_type=int(stats.get("n_struct_type", 0) or 0),
        n_interface_type=int(stats.get("n_interface_type", 0) or 0),
        n_import_declaration=int(stats.get("n_import_declaration", 0) or 0),
        n_function_item=int(stats.get("n_function_item", 0) or 0),
        n_impl_item=int(stats.get("n_impl_item", 0) or 0),
        n_struct_item=int(stats.get("n_struct_item", 0) or 0),
        n_trait_item=int(stats.get("n_trait_item", 0) or 0),
        n_use_declaration=int(stats.get("n_use_declaration", 0) or 0),
        type_decl_names=tdt,
    )


def compute_score(i: QualityInputs) -> float:
    """
    0.0 if no functions, classes, or imports; otherwise additive components
    capping at 1.0.
    """
    if i.n_functions == 0 and i.n_classes == 0 and i.n_imports == 0:
        return 0.0
    score = 0.0
    if i.n_functions >= 1:
        score += 0.3
    if i.n_call_edges >= 1:
        score += 0.2
    if i.n_imports >= 1:
        score += 0.2
    names = [x for x in i.function_class_names if x and not _name_looks_synthetic(x)]
    if names:
        score += 0.2
    if i.n_lines > 10 and i.n_lines > 0 and i.n_functions > 0:
        density = i.n_functions / i.n_lines
        if density > 0.05:
            score += 0.1
    return round(min(1.0, score), 4)


def compute_score_v2(i: QualityInputs, grammar: str) -> float:
    """
    Quality score using a per-grammar profile when present; ``generic`` fallback
    in :func:`load_profile`; if still missing, identical to :func:`compute_score`.
    """
    profile = load_profile(grammar)
    if profile is None:
        return compute_score(i)
    if profile.formula == "weighted_sum":
        # Legacy v1 short-circuit (Python only; same as :func:`compute_score` first line)
        if profile.grammar in ("python", "javascript"):
            if i.n_functions == 0 and i.n_classes == 0 and i.n_imports == 0:
                return 0.0
        return _apply_weighted_sum(i, profile)
    if profile.formula == "custom_python":
        return _apply_python_profile(i, profile)
    raise ValueError(f"unknown quality profile formula: {profile.formula!r}")
