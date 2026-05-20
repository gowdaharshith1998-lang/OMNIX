from __future__ import annotations

import json
from pathlib import Path


def write_program(root: Path, name: str = "HELLO", *, copy: str | None = None) -> Path:
    copy_line = f"    COPY {copy}.\n" if copy else ""
    source = root / f"{name}.cob"
    source.write_text(
        "IDENTIFICATION DIVISION.\n"
        f"PROGRAM-ID. {name}.\n"
        "DATA DIVISION.\n"
        "PROCEDURE DIVISION.\n"
        f"{copy_line}"
        f"    DISPLAY \"{name}\".\n"
        "    STOP RUN.\n",
        encoding="utf-8",
    )
    return source


def write_receipt(path: Path, program: str = "HELLO") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "node_fqn": program,
                "target_language": "python",
                "gate_results": [
                    {"gate_number": n, "gate_name": str(n), "status": "passed", "details": {}}
                    for n in range(1, 7)
                ],
            }
        ),
        encoding="utf-8",
    )
    path.with_suffix(".py").write_text("def main(stdin: bytes) -> bytes:\n    return b''\n", encoding="utf-8")
    path.with_suffix(".sig").write_text("sig\n", encoding="utf-8")

