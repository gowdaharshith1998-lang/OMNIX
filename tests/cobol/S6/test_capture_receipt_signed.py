from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from omnix.receipts.finding_keys import project_pubkey_path
from omnix.runtime.cobol.capture import ProgramRun, run_capture


def _runner(_program: Path, stdin_bytes: bytes, _cwd: Path, _timeout: float) -> ProgramRun:
    return ProgramRun(stdout=stdin_bytes, stderr=b"", returncode=0)


def test_capture_receipt_signed(tmp_path: Path) -> None:
    fx = tmp_path / "fx" / "fixture1"
    fx.mkdir(parents=True)
    (fx / "input.bin").write_bytes(b"abc")
    prog = tmp_path / "prog"
    prog.write_text("", encoding="utf-8")
    out = tmp_path / "out"
    run_capture(project_root=tmp_path, program=prog, fixtures_dir=tmp_path / "fx", output_root=out, runner=_runner)
    payload = json.loads((out / "fixture1.json").read_text(encoding="utf-8"))
    sig = base64.b64decode(payload["signature"], validate=True)
    unsigned = dict(payload)
    del unsigned["signature"]
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    pub = serialization.load_pem_public_key(project_pubkey_path(tmp_path).read_bytes())
    assert isinstance(pub, Ed25519PublicKey)
    pub.verify(sig, raw)
