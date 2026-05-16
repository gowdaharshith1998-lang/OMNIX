"""Phase 3b: calibration invariants and optional AXIOM-V2 smoke."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from omnix.parser.quality import (
    QualityInputs,
    compute_score,
    compute_score_v2,
)
from omnix.parser.quality_profiles import load_profile


def test_python_does_not_regress() -> None:
    # Representative small module: matches legacy v1 ballpark with non-synthetic name
    qi = QualityInputs(
        n_functions=1,
        n_classes=0,
        n_imports=1,
        n_call_edges=1,
        n_lines=20,
        function_class_names=("main",),
    )
    v1 = compute_score(qi)
    v2 = compute_score_v2(qi, "python")
    assert 0.70 <= v1 <= 0.95
    assert 0.70 <= v2 <= 0.95
    assert abs(v1 - v2) < 0.12


def test_typescript_type_only_file_scores_above_zero() -> None:
    # Legacy v1 ignores type-only decls: must have fn/class/import all zero for 0.0
    qi = QualityInputs(
        n_functions=0,
        n_classes=0,
        n_imports=0,
        n_call_edges=0,
        n_lines=12,
        function_class_names=(),
        n_interface_declaration=1,
        n_type_alias_declaration=1,
        n_enum_declaration=0,
        type_decl_names=("User", "ID"),
    )
    assert compute_score(qi) == 0.0
    s = compute_score_v2(qi, "typescript")
    assert s > 0.0
    assert s < 1.0


def test_typescript_runtime_file_still_scores_well() -> None:
    qi = QualityInputs(
        n_functions=2,
        n_classes=1,
        n_imports=1,
        n_call_edges=2,
        n_lines=80,
        function_class_names=("a", "b", "C"),
        n_interface_declaration=1,
        type_decl_names=("Row",),
    )
    assert compute_score_v2(qi, "typescript") >= 0.7


def test_unknown_grammar_uses_generic_profile() -> None:
    p = load_profile("klingon")
    assert p is not None
    assert p.grammar == "generic"
    assert p.formula == "weighted_sum"


@pytest.mark.skipif(
    os.environ.get("OMNIX_AXIOM_SMOKE", "") != "1"
    or not os.path.isdir(os.path.expanduser("~/AXIOM-V2")),
    reason="set OMNIX_AXIOM_SMOKE=1 and have ~/AXIOM-V2 (long-running analyze)",
)
def test_axiom_v2_python_and_typescript_aggregates() -> None:
    axiom = os.path.expanduser("~/AXIOM-V2")
    db = os.path.join(axiom, "omnix.db")
    if os.path.isfile(db):
        os.remove(db)
    r = subprocess.run(
        [sys.executable, os.path.join(_omnix_root(), "omnix.py"), "analyze", axiom, "--no-open"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert os.path.isfile(db), "omnix.db expected after analyze"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
    try:
        cur = con.execute(
            "SELECT grammar_name, total_files_parsed, total_quality_score "
            "FROM grammar_profile WHERE grammar_name IN (?,?)",
            ("python", "typescript"),
        )
        rows = {str(r[0]): (int(r[1] or 0), float(r[2] or 0.0)) for r in cur.fetchall()}
    finally:
        con.close()
    for g in ("python", "typescript"):
        assert g in rows, f"missing {g} in grammar_profile: {rows}"
        tf, tq = rows[g]
        assert tf > 0
        q = tq / tf
        if g == "python":
            assert 0.70 <= q <= 0.80, f"python avg_quality={q}"
        else:
            assert q >= 0.55, f"typescript avg_quality={q}"


def _omnix_root() -> str:
    # test file -> quality_profiles -> parser -> tests -> repo
    return str(Path(__file__).resolve().parents[3])
