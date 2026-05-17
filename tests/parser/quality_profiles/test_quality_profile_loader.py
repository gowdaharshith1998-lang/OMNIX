"""Phase 3a: profile loader (strict validation, resolution order)."""

from __future__ import annotations

import json

import pytest

from omnix.parser.quality_profiles import (
    QualityProfileValidationError,
    load_profile,
)


def test_loader_returns_none_when_no_profile_exists(tmp_path: Path) -> None:
    assert load_profile("python", _profiles_dir=tmp_path) is None
    assert load_profile("typescript", _profiles_dir=tmp_path) is None
    assert load_profile("cobol", _profiles_dir=tmp_path) is None


def test_loader_validates_weight_bounds(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(
        json.dumps(
            {
                "grammar": "x",
                "formula": "weighted_sum",
                "profile_version": 1,
                "weights": {"a": 2.0},
                "required_minimums": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(QualityProfileValidationError, match="weight for 'a'|2\\.0"):
        load_profile("x", _profiles_dir=tmp_path)


def test_loader_validates_weight_sum(tmp_path: Path) -> None:
    p = tmp_path / "y.json"
    p.write_text(
        json.dumps(
            {
                "grammar": "y",
                "formula": "weighted_sum",
                "profile_version": 1,
                "weights": {"a": 0.8, "b": 0.8},
                "required_minimums": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(QualityProfileValidationError, match="sum of weights"):
        load_profile("y", _profiles_dir=tmp_path)


def test_loader_python_takes_priority_over_json(tmp_path: Path) -> None:
    (tmp_path / "zorg.json").write_text(
        json.dumps(
            {
                "grammar": "zorg",
                "formula": "weighted_sum",
                "profile_version": 99,
                "weights": {"k": 1.0},
                "required_minimums": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "zorg.py").write_text(
        "def score(stats: dict) -> float:\n"
        "    return 0.0\n",
        encoding="utf-8",
    )
    prof = load_profile("zorg", _profiles_dir=tmp_path)
    assert prof is not None
    assert prof.formula == "custom_python"
    assert prof.profile_version == 1
    assert str(tmp_path / "zorg.py") in (prof.python_module or "")
