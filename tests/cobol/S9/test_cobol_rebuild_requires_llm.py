from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.parser.ingest_dispatch import ingest_unified_codebase
from omnix.rebuild.cobol_runner import (
    MissingLlmCredentialsError,
    iter_cobol_programs,
    rebuild_cobol_program,
)


def _write_program(root: Path) -> Path:
    source = root / "HELLO.cob"
    source.write_text(
        """IDENTIFICATION DIVISION.
PROGRAM-ID. HELLO.
PROCEDURE DIVISION.
    DISPLAY "HELLO".
    STOP RUN.
""",
        encoding="utf-8",
    )
    return source


def _write_capture(root: Path) -> None:
    capture_dir = root / ".omnix" / "captures" / "cobol" / "HELLO"
    capture_dir.mkdir(parents=True)
    (capture_dir / "empty.json").write_text(
        json.dumps(
            {
                "fixture_id": "empty",
                "stdin_b64": base64.b64encode(b"").decode("ascii"),
                "stdout_b64": base64.b64encode(b"HELLO\n").decode("ascii"),
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )


def test_cobol_rebuild_requires_llm_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_program(tmp_path)
    _write_capture(tmp_path)
    db_dir = tmp_path / ".omnix"
    db_dir.mkdir(exist_ok=True)
    store = GraphStore(str(db_dir / "omnix.db"))
    ingest_unified_codebase(str(tmp_path), store)
    programs = iter_cobol_programs(store, tmp_path, node_filter="*HELLO*")

    for env_name in ("OMNIX_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(MissingLlmCredentialsError, match="COBOL rebuild requires LLM credentials"):
        rebuild_cobol_program(
            store=store,
            program_node_id=programs[0].node_id,
            target_language="python",
            receipts_dir=tmp_path / ".omnix" / "receipts" / "cobol",
            project_path=tmp_path,
        )
    store.close()
