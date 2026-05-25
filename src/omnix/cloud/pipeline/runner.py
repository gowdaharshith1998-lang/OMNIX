"""Pipeline runner — composes (but never modifies) the existing M1 orchestrator.

This module is the bridge between the cloud surface and the existing OMNIX
core. It MUST NOT import from or mutate:
  * src/omnix/orchestrator/ (M1)
  * src/omnix/gates/gate6_behavioral.py (M2 gate 6)
  * .omnix/receipts/ tree

Subprocess isolation is enforced for the M1 invocation so that a buggy gate
cannot take down the cloud API.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from omnix.cloud import events


@dataclass
class PipelineResult:
    job_id: str
    state: str
    gates_completed: list[str]
    receipts: list[dict]


def _emit(job_id: str, gate: str, message: str, *, severity: str = "info", **payload):
    events.publish(job_id, gate, message, severity=severity, payload=payload)


def _materialize_workspace(
    workspace: str | None,
    artifact_storage_key: str | None,
    job_id: str,
) -> str:
    if workspace:
        return workspace
    if artifact_storage_key:
        from omnix.cloud.ingest.storage import get_storage

        backend = get_storage()
        data = backend.get_object(artifact_storage_key)
        # Persist into a per-job scratch dir; the M1 entry expects a directory.
        out = Path(f"/tmp/omnix-jobs/{job_id}/in")
        out.mkdir(parents=True, exist_ok=True)
        (out / "bundle.bin").write_bytes(data)
        return str(out)
    raise RuntimeError("no workspace or artifact provided to pipeline")


def _run_m1_subprocess(workspace: str, job_id: str, target_language: str) -> dict:
    """Invoke the existing M1 orchestrator as a subprocess.

    We deliberately use the OMNIX CLI to dispatch, not the orchestrator's
    Python module: subprocess isolation + CLI surface stability.
    """
    cmd = [
        sys.executable,
        "-m",
        "omnix.cli",
        "rebuild",
        "--input",
        workspace,
        "--target",
        target_language,
        "--json",
    ]
    _emit(job_id, "ingest", f"M1 invoke: {shlex.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60 * 60 * 3,
        )
    except subprocess.TimeoutExpired:
        _emit(job_id, "error", "M1 pipeline timed out after 3h", severity="error")
        raise

    if proc.returncode != 0:
        _emit(
            job_id,
            "error",
            "M1 pipeline exited non-zero",
            severity="error",
            stderr_tail=proc.stderr[-2048:],
        )
        return {"ok": False, "stderr": proc.stderr, "stdout": proc.stdout}

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout_raw": proc.stdout}


def run_pipeline(
    *,
    job_id: str,
    workspace: str | None,
    artifact_storage_key: str | None,
    tenant_id: str | None,
    source_repo: str | None = None,
    source_sha: str | None = None,
    source_sha256: str | None = None,
    target_language: str = "java21",
    dry_run: bool = False,
) -> dict:
    _emit(job_id, "ingest", "ingestion complete", source_repo=source_repo,
          source_sha=source_sha, source_sha256=source_sha256)

    ws = _materialize_workspace(workspace, artifact_storage_key, job_id)
    _emit(job_id, "parse", f"workspace materialized: {ws}")

    if dry_run:
        # Tests-only: simulate the gate progression without subprocess.
        _emit(job_id, "spec", "spec mining (dry-run)")
        _emit(job_id, "generate", "generation (dry-run)")
        _emit(job_id, "verify", "verification (dry-run)")
        _emit(job_id, "cutover", "awaiting cutover authorization (dry-run)",
              severity="success")
        return {
            "job_id": job_id,
            "state": "awaiting_cutover",
            "gates_completed": ["ingest", "parse", "spec", "generate", "verify"],
            "receipts": [],
        }

    m1 = _run_m1_subprocess(ws, job_id, target_language)
    if not m1.get("ok", True):
        _emit(job_id, "error", "M1 rebuild failed", severity="error")
        return {"job_id": job_id, "state": "failed", "m1": m1, "receipts": []}

    _emit(job_id, "verify", "M1 rebuild completed", severity="success",
          gates=m1.get("gates", []))

    # Gather signed receipts emitted by the existing pipeline. The M1 stage
    # writes them under .omnix/receipts/ — read-only and uncopied here. We only
    # collect their metadata for the cloud Receipt rows.
    receipts: list[dict] = []
    receipts_dir = Path(".omnix/receipts")
    if receipts_dir.exists():
        for receipt_json in receipts_dir.rglob("*.json"):
            try:
                receipts.append(json.loads(receipt_json.read_text()))
            except Exception:  # noqa: BLE001
                continue

    _emit(job_id, "complete", "pipeline complete", severity="success",
          receipt_count=len(receipts))

    return {
        "job_id": job_id,
        "state": "awaiting_cutover",
        "gates_completed": ["ingest", "parse", "spec", "generate", "verify"],
        "receipts": receipts[:50],  # cap to keep the response light
    }
