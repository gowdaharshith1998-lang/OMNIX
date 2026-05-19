from __future__ import annotations

from pathlib import Path

from omnix.parser.ingest_dispatch import ingest_one_path_parse_only
from omnix.runtime.cobol.ebcdic import detect_ebcdic, normalize_ebcdic


def test_tc301e_ebcdic_fixture_ingests_as_cobol() -> None:
    root = Path("tests/fixtures/cobol/nist").resolve()
    source = root / "TC301E.cob.ebcdic"
    raw = source.read_bytes()

    assert detect_ebcdic(raw)
    assert normalize_ebcdic(raw) == (root / "TC301E.cob").read_text(encoding="utf-8")

    result = ingest_one_path_parse_only((0, str(root), str(source), "generic"))

    assert result["status"] == "ok"
    assert result["grammar_name"] == "cobol"
    assert result["inferred_lang"] == "cobol"
    assert result["n_snap_nodes"] > 0
