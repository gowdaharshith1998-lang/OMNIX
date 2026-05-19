"""Gate 6 behavioral diff for COBOL capture parity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BehavioralDiff:
    passed: bool
    stdout_equal: bool
    exit_equal: bool
    files_equal: bool
    details: dict[str, object] = field(default_factory=dict)


def compare_behavior(
    *,
    legacy_stdout: bytes,
    legacy_exit: int,
    legacy_files: dict[str, bytes],
    candidate_stdout: bytes,
    candidate_exit: int,
    candidate_files: dict[str, bytes],
) -> BehavioralDiff:
    stdout_equal = legacy_stdout == candidate_stdout
    exit_equal = legacy_exit == candidate_exit
    legacy_h = {k: hashlib.sha256(v).hexdigest() for k, v in legacy_files.items()}
    cand_h = {k: hashlib.sha256(v).hexdigest() for k, v in candidate_files.items()}
    files_equal = legacy_h == cand_h
    return BehavioralDiff(
        passed=stdout_equal and exit_equal and files_equal,
        stdout_equal=stdout_equal,
        exit_equal=exit_equal,
        files_equal=files_equal,
        details={"legacy_files": legacy_h, "candidate_files": cand_h},
    )


def capture_output_files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for p in root.rglob("*"):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_bytes()
    return out
