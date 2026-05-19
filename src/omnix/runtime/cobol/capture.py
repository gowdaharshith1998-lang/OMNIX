"""COBOL fixture execution + signed capture manifest."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omnix.receipts.finding_keys import ensure_project_key, project_privkey_path
from omnix.receipts.finding_receipt import compute_project_id, now_iso8601_utc
from omnix.runtime.cobol.gnucobol_adapter import ProgramRun


@dataclass(frozen=True)
class CaptureResult:
    fixture_id: str
    manifest_path: Path


Runner = Callable[[Path, bytes, Path, float], ProgramRun]


def _default_runner(program: Path, stdin_bytes: bytes, cwd: Path, timeout_s: float) -> ProgramRun:
    from omnix.runtime.cobol.gnucobol_adapter import run_cobol

    return run_cobol(program, stdin_bytes=stdin_bytes, cwd=cwd, timeout_s=timeout_s)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign_manifest(project_root: Path, payload: dict[str, object]) -> str:
    ensure_project_key(project_root)
    project_id = compute_project_id(project_root)
    priv_path = project_privkey_path(project_id)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("project key is not Ed25519")
    sig = key.sign(raw)
    return base64.b64encode(sig).decode("ascii")


def run_capture(
    *,
    project_root: Path,
    program: Path,
    fixtures_dir: Path,
    output_root: Path,
    timeout_s: float = 10.0,
    runner: Runner | None = None,
) -> list[CaptureResult]:
    run_impl = runner or _default_runner
    output_root.mkdir(parents=True, exist_ok=True)
    out: list[CaptureResult] = []
    for fx in sorted(fixtures_dir.iterdir()):
        if not fx.is_dir():
            continue
        desc = fx / "input.bin"
        if not desc.is_file():
            continue
        stdin_b = desc.read_bytes()
        pr = run_impl(program, stdin_b, fx, timeout_s)
        payload: dict[str, object] = {
            "program": program.name,
            "fixture_id": fx.name,
            "timestamp": now_iso8601_utc(),
            "stdin_sha256": _sha(stdin_b),
            "stdin_b64": base64.b64encode(stdin_b).decode("ascii"),
            "stdout_sha256": _sha(pr.stdout),
            "stdout_b64": base64.b64encode(pr.stdout).decode("ascii"),
            "exit_code": int(pr.returncode),
            "file_reads": [],
            "file_writes": [
                {"path": "stdout", "bytes_sha256": _sha(pr.stdout)}
            ],
        }
        payload["signature"] = _sign_manifest(project_root, payload)
        out_path = output_root / f"{fx.name}.json"
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        out.append(CaptureResult(fixture_id=fx.name, manifest_path=out_path))
    return out
