"""
Per-grammar quality profiles (JSON or Python) — loaded by :func:`load_profile`.

``quality.py`` imports this package; this package does **not** import ``quality``
(import-cycle safe).
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Final

_PROFILES_DIR: Path = Path(__file__).resolve().parent

_WEIGHT_SUM_TOLERANCE: Final = 0.01


@dataclass(frozen=True)
class QualityProfile:
    """Loaded profile. ``custom_python`` profiles may leave ``weights`` empty."""

    grammar: str
    weights: dict[str, float]
    required_minimums: dict[str, int]
    formula: str  # "weighted_sum" | "custom_python"
    python_module: str | None  # set if formula == "custom_python" (file path)
    profile_version: int


class QualityProfileValidationError(ValueError):
    """Profile file failed validation (path + reason in ``args``)."""


def _validate_weights(path: Path, raw_weights: Any) -> dict[str, float]:
    if not isinstance(raw_weights, dict) or not all(
        isinstance(k, str) for k in raw_weights
    ):
        raise QualityProfileValidationError(
            f"{path}: weights must be a JSON object with string keys"
        )
    out: dict[str, float] = {}
    for k, v in raw_weights.items():
        if not isinstance(v, (int, float)):
            raise QualityProfileValidationError(
                f"{path}: weight for {k!r} must be numeric"
            )
        fv = float(v)
        if fv < 0.0 or fv > 1.0:
            raise QualityProfileValidationError(
                f"{path}: weight for {k!r} must be in [0, 1], got {fv}"
            )
        out[k] = fv
    s = sum(out.values())
    if s > 1.0 + _WEIGHT_SUM_TOLERANCE:
        raise QualityProfileValidationError(
            f"{path}: sum of weights {s} exceeds 1.0 (tolerance {_WEIGHT_SUM_TOLERANCE})"
        )
    return out


def _validate_minimums(path: Path, raw: Any) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) for k in raw
    ):
        raise QualityProfileValidationError(
            f"{path}: required_minimums must be a JSON object with string keys"
        )
    out: dict[str, int] = {}
    for k, v in raw.items():
        if not isinstance(v, int) or v < 0:
            raise QualityProfileValidationError(
                f"{path}: required_minimums[{k!r}] must be a non-negative int"
            )
        out[k] = v
    return out


def _load_json_profile(path: Path, grammar: str) -> QualityProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise QualityProfileValidationError(f"{path}: cannot read JSON: {e}") from e
    if not isinstance(data, dict):
        raise QualityProfileValidationError(f"{path}: root must be a JSON object")
    g = str(data.get("grammar", "")).strip()
    if g != grammar:
        raise QualityProfileValidationError(
            f"{path}: grammar field {g!r} does not match filename (expected {grammar!r})"
        )
    formula = str(data.get("formula", "")).strip()
    if formula not in ("weighted_sum", "custom_python"):
        raise QualityProfileValidationError(
            f"{path}: formula must be 'weighted_sum' or 'custom_python', got {formula!r}"
        )
    w = _validate_weights(path, data.get("weights", {}))
    mins = _validate_minimums(path, data.get("required_minimums", {}))
    pver = int(data.get("profile_version", 1))
    if pver < 1:
        raise QualityProfileValidationError(
            f"{path}: profile_version must be >= 1, got {pver}"
        )
    pmod: str | None
    if formula == "custom_python":
        pmod = str(
            data.get("python_module") or path.with_suffix(".py")
        )
    else:
        pmod = None
    return QualityProfile(
        grammar=grammar,
        weights=w,
        required_minimums=mins,
        formula=formula,
        python_module=pmod,
        profile_version=pver,
    )


def _load_score_callable(python_path: Path) -> Callable[..., float]:
    name = f"_omnix_qprof_{python_path.stem}"
    spec = importlib.util.spec_from_file_location(name, python_path)
    if spec is None or spec.loader is None:
        raise QualityProfileValidationError(
            f"{python_path}: cannot load as Python module"
        )
    mod: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "score", None)
    if not callable(fn):
        raise QualityProfileValidationError(
            f"{python_path}: must export a callable 'score' function"
        )
    return mod.score  # type: ignore[no-any-return, union-attr]


def _resolve_profiles_dir(override: Path | None) -> Path:
    return override if override is not None else _PROFILES_DIR


def load_profile(
    grammar: str, *, _profiles_dir: Path | None = None
) -> QualityProfile | None:
    """
    Return a :class:`QualityProfile` for ``grammar``, or ``None`` for legacy fallback.

    Resolution (under ``src/omnix/parser/quality_profiles/`` unless *\\_profiles_dir* is
    set for tests):

    1. ``<grammar>.py`` — must define ``score(…)``; takes priority if present
    2. ``<grammar>.json`` — validated declarative profile
    3. ``generic.json`` — if no file for ``grammar`` (unknown or future language)
    4. ``None`` only if there is no ``generic.json`` (caller uses :func:`omnix.parser.quality.compute_score`)

    On validation failure, raises :class:`QualityProfileValidationError` (no silent
    fallback to legacy).
    """
    g = (grammar or "").strip()
    if not g:
        return None
    base = _resolve_profiles_dir(_profiles_dir)
    p_py = base / f"{g}.py"
    p_json = base / f"{g}.json"
    if p_py.is_file():
        if p_py.stem != g:
            raise QualityProfileValidationError(
                f"{p_py}: file stem {p_py.stem!r} must match grammar {g!r}"
            )
        _ = _load_score_callable(p_py)
        return QualityProfile(
            grammar=g,
            weights={},
            required_minimums={},
            formula="custom_python",
            python_module=str(p_py),
            profile_version=1,
        )
    if p_json.is_file():
        return _load_json_profile(p_json, g)
    p_generic = base / "generic.json"
    if p_generic.is_file():
        return _load_json_profile(p_generic, "generic")
    return None


def load_custom_score(path: str | Path) -> Callable[..., float]:
    """Load ``score`` from a profile ``.py`` file (used by :func:`compute_score_v2`)."""
    return _load_score_callable(Path(path))
