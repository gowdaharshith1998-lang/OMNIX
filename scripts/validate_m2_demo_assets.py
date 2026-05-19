#!/usr/bin/env python3
"""Validate M2 demo artifacts without creating or modifying them.

The Phase 8 assets must come from a real operator-run rebuild and a single
asciinema take. This script only checks that the committed files are complete
and internally consistent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CAST_MIN_SECONDS = 70.0
CAST_MAX_SECONDS = 95.0

FORBIDDEN_BRIEF_PHRASES = (
    "revolutionary",
    "game-changing",
    "ai-first",
)

SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{24,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_./+=-]{12,}"),
)


def _docs_dir(repo_root: Path) -> Path:
    return repo_root / "docs"


def _load_json(path: Path, errors: list[str]) -> Any:
    if not path.is_file():
        errors.append(f"missing required file: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: malformed JSON: {exc}")
        return None


def _gate(receipt: dict[str, Any], gate_number: int) -> dict[str, Any] | None:
    for gate in receipt.get("gate_results", []):
        if gate.get("gate_number") == gate_number:
            return gate
    return None


def _walk_keys(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        keys: list[str] = []
        for key, child in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(key_path)
            keys.extend(_walk_keys(child, key_path))
        return keys
    if isinstance(value, list):
        keys = []
        for idx, child in enumerate(value):
            keys.extend(_walk_keys(child, f"{prefix}[{idx}]"))
        return keys
    return []


def _check_receipt_samples(repo_root: Path, errors: list[str]) -> None:
    docs = _docs_dir(repo_root)
    passed = _load_json(docs / "m2_demo_receipt_sample_passed.json", errors)
    failed = _load_json(docs / "m2_demo_receipt_sample_failed.json", errors)
    for name, receipt in (("passed", passed), ("failed", failed)):
        if not isinstance(receipt, dict):
            continue
        for key_path in _walk_keys(receipt):
            lowered = key_path.lower()
            if "cost" in lowered and ("usd" in lowered or "dollar" in lowered):
                errors.append(f"{name} receipt includes a cost-dollar field: {key_path}")
        gate6 = _gate(receipt, 6)
        if gate6 is None:
            errors.append(f"{name} receipt is missing gate 6")
            continue
        if name == "passed" and gate6.get("status") != "passed":
            errors.append("passed receipt gate 6 must have status 'passed'")
        if name == "failed":
            if gate6.get("status") != "failed":
                errors.append("failed receipt gate 6 must have status 'failed'")
            details = gate6.get("details")
            if not isinstance(details, dict) or "diverging_input" not in details:
                errors.append("failed receipt gate 6 must include details.diverging_input")


def _cast_output(path: Path, errors: list[str]) -> tuple[float | None, str]:
    if not path.is_file():
        errors.append(f"missing required file: {path}")
        return None, ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        errors.append(f"{path}: cast is empty")
        return None, ""
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid asciinema header: {exc}")
        return None, ""
    if header.get("version") != 2:
        errors.append(f"{path}: expected asciinema v2 header")

    max_time = 0.0
    output_chunks: list[str] = []
    for lineno, line in enumerate(lines[1:], start=2):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{lineno}: invalid asciinema event: {exc}")
            continue
        if not (
            isinstance(event, list)
            and len(event) == 3
            and isinstance(event[0], (int, float))
        ):
            errors.append(f"{path}:{lineno}: invalid asciinema event shape")
            continue
        max_time = max(max_time, float(event[0]))
        if event[1] == "o" and isinstance(event[2], str):
            output_chunks.append(event[2])
    return max_time, "".join(output_chunks)


def _check_cast(repo_root: Path, errors: list[str]) -> None:
    duration, output = _cast_output(_docs_dir(repo_root) / "m2_demo.cast", errors)
    if duration is None:
        return
    if not CAST_MIN_SECONDS <= duration <= CAST_MAX_SECONDS:
        errors.append(
            f"docs/m2_demo.cast duration {duration:.1f}s is outside "
            f"{CAST_MIN_SECONDS:.0f}-{CAST_MAX_SECONDS:.0f}s"
        )
    lowered = output.lower()
    required_fragments = (
        "27 receipt",
        "verified",
        "gate6",
        "failed",
        "diverging_input",
    )
    for fragment in required_fragments:
        if fragment not in lowered:
            errors.append(f"docs/m2_demo.cast output missing {fragment!r}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(output):
            errors.append(f"docs/m2_demo.cast appears to expose a secret: {pattern.pattern}")


def _check_docs(repo_root: Path, errors: list[str]) -> None:
    docs = _docs_dir(repo_root)
    demo_path = docs / "M2_DEMO.md"
    brief_path = docs / "YC_APPLICATION_BRIEF.md"
    if not demo_path.is_file():
        errors.append(f"missing required file: {demo_path}")
    else:
        demo = demo_path.read_text(encoding="utf-8").lower()
        if "omnix caught a real bug" not in demo:
            errors.append("docs/M2_DEMO.md must explain that OMNIX caught a real bug")
        if "not omnix is broken" not in demo:
            errors.append("docs/M2_DEMO.md must say the failure is not OMNIX is broken")
    if not brief_path.is_file():
        errors.append(f"missing required file: {brief_path}")
    else:
        brief = brief_path.read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_BRIEF_PHRASES:
            if phrase in brief:
                errors.append(f"docs/YC_APPLICATION_BRIEF.md contains banned phrase {phrase!r}")


def validate(repo_root: Path) -> list[str]:
    """Return validation errors for the Phase 8 demo artifact set."""
    errors: list[str] = []
    _check_receipt_samples(repo_root, errors)
    _check_cast(repo_root, errors)
    _check_docs(repo_root, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root containing docs/",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("M2 demo assets validate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
