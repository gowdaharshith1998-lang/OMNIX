# Compliance: P11, P15, P19, P20, P22

"""
PEM wrapping for OMNIX AXIOM ML-DSA-65 (raw FIPS-204 key/signature bytes).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from . import params as P

PUB_PEM = "OMNIX-AXIOM ML-DSA-65 PUBLIC KEY"
SEC_PEM = "OMNIX-AXIOM ML-DSA-65 SECRET KEY"
SIG_PEM = "OMNIX-AXIOM ML-DSA-65 SIGNATURE"


def _pem_wrap(kind: str, raw: bytes) -> str:
    b64 = base64.encodebytes(raw).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    return (
        f"-----BEGIN {kind}-----\n"
        + "\n".join(lines)
        + f"\n-----END {kind}-----\n"
    )


def _pem_unwrap(pem: str, kind: str) -> bytes:
    m = f"-----BEGIN {kind}-----"
    n = f"-----END {kind}-----"
    if m not in pem or n not in pem:
        raise ValueError("invalid PEM")
    body = pem.split(m, 1)[1].split(n, 1)[0]
    s = "".join(line.strip() for line in body.splitlines() if line.strip())
    return base64.b64decode(s, validate=True)


def public_to_pem(pk: bytes) -> str:
    if len(pk) != P.PK_SIZE:
        raise ValueError("public key size")
    return _pem_wrap(PUB_PEM, pk)


def secret_to_pem(sk: bytes) -> str:
    if len(sk) != P.SK_SIZE:
        raise ValueError("secret key size")
    return _pem_wrap(SEC_PEM, sk)


def signature_to_pem(sig: bytes) -> str:
    if len(sig) != P.SIG_SIZE:
        raise ValueError("signature size")
    return _pem_wrap(SIG_PEM, sig)


def public_from_pem(pem: str) -> bytes:
    b = _pem_unwrap(pem, PUB_PEM)
    if len(b) != P.PK_SIZE:
        raise ValueError("decoded pk size")
    return b


def secret_from_pem(pem: str) -> bytes:
    b = _pem_unwrap(pem, SEC_PEM)
    if len(b) != P.SK_SIZE:
        raise ValueError("decoded sk size")
    return b


def signature_from_pem(pem: str) -> bytes:
    b = _pem_unwrap(pem, SIG_PEM)
    if len(b) != P.SIG_SIZE:
        raise ValueError("decoded sig size")
    return b


def write_keypair_dir(out: Path) -> None:
    """Write public.pem and secret.pem (mode 0o600) for current key in caller."""
    from . import keygen  # import after subsystems ready

    out = out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    pk, sk = keygen.keygen()
    p_pub = out / "public.pem"
    p_sec = out / "secret.pem"
    p_pub.write_text(public_to_pem(pk), encoding="ascii")
    p_sec.write_text(secret_to_pem(sk), encoding="ascii")
    os.chmod(p_sec, 0o600)
