from __future__ import annotations

import json

from omnix.provenance.sidecar import write_sidecar
from omnix.provenance.signer import SidecarSigner, verify_sidecar_signature


def test_sidecar_signature_round_trip(tmp_path) -> None:
    (tmp_path / ".omnix").mkdir()
    signer = SidecarSigner(tmp_path)
    payload = {"schema_version": "omnix.provenance.v1", "target_program_id": "HELLO"}
    sidecar, sig = write_sidecar(tmp_path, "HELLO", payload, signer)
    assert verify_sidecar_signature(
        json.loads(sidecar.read_text(encoding="utf-8")),
        sig.read_text(encoding="utf-8").strip(),
        tmp_path / ".omnix" / "pubkey.pem",
    )
