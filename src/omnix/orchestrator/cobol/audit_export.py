"""Audit artifact export for COBOL orchestrator runs."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from omnix.orchestrator.cobol.run_state import RunState


def export_audit_zip(
    *,
    run_state: RunState,
    out_path: Path,
    include_replicas: bool = True,
    include_captures: bool = False,
) -> Path:
    verified = [row for row in run_state.all_programs() if row.state == "verified" and row.receipt_path]
    if not verified:
        raise ValueError("no verified receipts available for audit export")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run_state.run_id,
        "codebase_root": str(run_state.codebase_root),
        "programs": [row.__dict__ | {"spend_usd": str(row.spend_usd)} for row in run_state.all_programs()],
    }
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", _readme(run_state.run_id))
        zf.writestr("verify.py", _verify_script())
        zf.writestr("run_summary.json", json.dumps(summary, indent=2, sort_keys=True))
        pub = run_state.codebase_root / ".omnix" / "pubkey.pem"
        zf.writestr("public_key.pem", pub.read_text(encoding="utf-8") if pub.is_file() else "")
        for row in verified:
            receipt = Path(str(row.receipt_path))
            zf.write(receipt, f"receipts/{receipt.name}")
            sig = receipt.with_suffix(".sig")
            if sig.is_file():
                zf.write(sig, f"receipts/{sig.name}")
            if include_replicas:
                replica = receipt.with_suffix(".py")
                if replica.is_file():
                    zf.write(replica, f"replicas/{replica.name}")
        if include_captures:
            captures = run_state.codebase_root / ".omnix" / "captures" / "cobol"
            if captures.is_dir():
                for path in captures.rglob("*.json"):
                    zf.write(path, f"captures/{path.relative_to(captures).as_posix()}")
    return out_path


def copy_receipt_to_run(receipt: Path, run_receipts_dir: Path) -> Path:
    run_receipts_dir.mkdir(parents=True, exist_ok=True)
    dest = run_receipts_dir / receipt.name
    shutil.copy2(receipt, dest)
    for suffix in (".sig", ".py"):
        sibling = receipt.with_suffix(suffix)
        if sibling.is_file():
            shutil.copy2(sibling, dest.with_suffix(suffix))
    return dest


def _readme(run_id: str) -> str:
    return (
        f"# OMNIX COBOL Audit Export\n\n"
        f"Run: `{run_id}`\n\n"
        "Run `python3 verify.py` from this directory to validate receipt signatures "
        "when `cryptography` is available.\n"
    )


def _verify_script() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
except Exception as exc:
    print(f"cryptography unavailable: {exc}", file=sys.stderr)
    sys.exit(1)


def canonical(payload: dict) -> bytes:
    payload = dict(payload)
    payload["gate_results"] = sorted(payload.get("gate_results", []), key=lambda g: int(g["gate_number"]))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main() -> int:
    pub_path = Path("public_key.pem")
    if not pub_path.is_file() or not pub_path.read_text(encoding="utf-8").strip():
        print("public_key.pem missing")
        return 1
    key = serialization.load_pem_public_key(pub_path.read_bytes())
    failures = 0
    receipts = sorted(Path("receipts").glob("*.json"))
    for receipt in receipts:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        sig = base64.b64decode(receipt.with_suffix(".sig").read_text(encoding="utf-8").strip(), validate=True)
        try:
            key.verify(sig, canonical(payload))
            gates_ok = all(g.get("status") == "passed" for g in payload.get("gate_results", []))
            print(f"{receipt.name}: {'OK' if gates_ok else 'GATE_FAIL'}")
            failures += 0 if gates_ok else 1
        except InvalidSignature:
            print(f"{receipt.name}: BAD_SIGNATURE")
            failures += 1
    if not receipts:
        print("no receipts")
        return 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
'''

