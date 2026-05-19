from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest

from omnix.rebuild.cobol_runner import CobolProgram, _gate6_behavioral


def test_cobol_rebuild_gate6_fails_on_stdout_byte_diff(tmp_path: Path) -> None:
    if shutil.which("cobc") is None:
        pytest.skip("cobc is required for real Gate 6 behavioral checks")

    source = tmp_path / "HELLO.cob"
    source.write_text(
        """IDENTIFICATION DIVISION.
PROGRAM-ID. HELLO.
PROCEDURE DIVISION.
    DISPLAY "HELLO".
    STOP RUN.
""",
        encoding="utf-8",
    )
    program = CobolProgram(
        node_id="HELLO::CobolProgram::HELLO",
        name="HELLO",
        source_path=source,
        source_text=source.read_text(encoding="utf-8"),
    )
    capture = {
        "fixture_id": "empty",
        "stdin_b64": base64.b64encode(b"").decode("ascii"),
        "stdout_b64": base64.b64encode(b"HELLO\n").decode("ascii"),
        "exit_code": 0,
    }
    bad_replica = """def main(stdin: bytes) -> bytes:
    return b"WRONG\\n"

if __name__ == "__main__":
    import sys
    sys.stdout.buffer.write(main(sys.stdin.buffer.read()))
"""

    result = _gate6_behavioral(program, bad_replica, [capture])

    assert result.status == "failed"
    assert result.gate_number == 6
    assert result.details["failures"][0]["legacy_stdout"] == "HELLO\n"
    assert result.details["failures"][0]["candidate_stdout"] == "WRONG\n"
