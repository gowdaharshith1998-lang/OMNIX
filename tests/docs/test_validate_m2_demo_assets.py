from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_m2_demo_assets import validate


def _receipt(*, gate6_status: str, details: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "node_fqn": "org.apache.commons.lang.StringUtils.split",
        "model": "claude-opus-4.7",
        "gate_results": [
            {"gate_number": 1, "status": "passed"},
            {"gate_number": 2, "status": "passed"},
            {"gate_number": 3, "status": "passed"},
            {"gate_number": 4, "status": "passed"},
            {"gate_number": 5, "status": "passed"},
            {"gate_number": 6, "status": gate6_status, "details": details or {}},
        ],
    }


def _write_valid_assets(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir()
    (docs / "m2_demo_receipt_sample_passed.json").write_text(
        json.dumps(_receipt(gate6_status="passed")),
        encoding="utf-8",
    )
    (docs / "m2_demo_receipt_sample_failed.json").write_text(
        json.dumps(
            _receipt(
                gate6_status="failed",
                details={"classification": "value_diverge", "diverging_input": ["x"]},
            )
        ),
        encoding="utf-8",
    )
    header = {"version": 2, "width": 100, "height": 30}
    events = [
        [1.0, "o", "omnix rebuild ...\n"],
        [10.0, "o", "27 receipt(s) written\n"],
        [20.0, "o", '{"verified": true, "gates_summary": "6-passed"}\n'],
        [80.0, "o", 'gate6: failed {"diverging_input":["x"]}\n'],
    ]
    (docs / "m2_demo.cast").write_text(
        "\n".join(json.dumps(line) for line in [header, *events]) + "\n",
        encoding="utf-8",
    )
    (docs / "M2_DEMO.md").write_text(
        "Gate 6 failed means OMNIX caught a real bug, not OMNIX is broken.\n",
        encoding="utf-8",
    )
    (docs / "YC_APPLICATION_BRIEF.md").write_text(
        "OMNIX records signed rebuild receipts and reports gate outcomes.\n",
        encoding="utf-8",
    )


def test_validate_m2_demo_assets_accepts_complete_fixture(tmp_path: Path) -> None:
    _write_valid_assets(tmp_path)

    assert validate(tmp_path) == []


def test_validate_m2_demo_assets_rejects_missing_live_artifacts(tmp_path: Path) -> None:
    errors = validate(tmp_path)

    assert any("m2_demo.cast" in error for error in errors)
    assert any("m2_demo_receipt_sample_passed.json" in error for error in errors)
    assert any("M2_DEMO.md" in error for error in errors)


def test_validate_m2_demo_assets_rejects_secret_like_cast_output(tmp_path: Path) -> None:
    _write_valid_assets(tmp_path)
    cast = tmp_path / "docs" / "m2_demo.cast"
    cast.write_text(
        cast.read_text(encoding="utf-8")
        + json.dumps([81.0, "o", "api_key=sk-proj-abcdefghijklmnopqrstuvwxyz\n"])
        + "\n",
        encoding="utf-8",
    )

    errors = validate(tmp_path)

    assert any("secret" in error for error in errors)


def test_validate_m2_demo_assets_rejects_unsupported_yc_language(tmp_path: Path) -> None:
    _write_valid_assets(tmp_path)
    (tmp_path / "docs" / "YC_APPLICATION_BRIEF.md").write_text(
        "This would be game-changing.\n",
        encoding="utf-8",
    )

    errors = validate(tmp_path)

    assert any("game-changing" in error for error in errors)
