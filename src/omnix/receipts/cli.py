# Compliance: P18, P21, P22, P23

"""Click commands: `omnix axiom keygen|sign|verify|verify-finding|verify-scan|export-vault`."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import click

from . import keystore, sign
from . import verify as vfy

_DEFAULT_KEY_DIR = Path.home() / ".omnix" / "keys"
_DEFAULT_MLDSA_PUB = Path.home() / ".omnix" / "keys" / "public.pem"


def _discover_ed25519_pubkey(start: Path) -> Path | None:
    """Walk parents from ``start`` for ``.omnix/pubkey.pem``."""
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    visited: set[Path] = set()
    while cur not in visited:
        visited.add(cur)
        cand = cur / ".omnix" / "pubkey.pem"
        if cand.is_file():
            return cand.resolve()
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _manifest_scan_summary(scan_dir: Path) -> tuple[int, dict]:
    """Read ``finding_count`` and a safe manifest summary dict (no raw leaves)."""
    mp = scan_dir / "scan_manifest.json"
    if not mp.is_file():
        return 0, {}
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0, {}
    fc = int(m.get("finding_count") or 0)
    summary = {
        "finding_count": fc,
        "scan_summary": m.get("scan_summary", {}),
        "merkle_root": m.get("merkle_root"),
    }
    return fc, summary


@click.group("axiom")
def axiom_group() -> None:
    """AXIOM: ML-DSA-65 (evolution receipts) and Ed25519 project keys (finding receipts)."""


@axiom_group.command("keygen")
@click.option(
    "--out",
    "out_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="ML-DSA (legacy): write public.pem and secret.pem into this directory.",
)
@click.option(
    "--project",
    "project_path",
    type=click.Path(path_type=Path, exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Ed25519 project key: repository root (default: cwd). Used when --out is omitted.",
)
def cmd_keygen(out_dir: Path | None, project_path: Path) -> None:
    if out_dir is not None:
        try:
            out_dir = out_dir.expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            test = out_dir / ".omnix_write_test"
            try:
                test.write_text("x", encoding="ascii")
                test.unlink()
            except OSError as e:
                click.echo(f"not writable: {out_dir}: {e}", err=True)
                raise SystemExit(1) from e
            keystore.write_keypair_dir(out_dir)
        except OSError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1) from e
        return

    from .finding_keys import ensure_project_key
    from .finding_receipt import compute_project_id

    try:
        project_root = project_path.expanduser().resolve(strict=True)
        project_id = compute_project_id(project_root)
        _priv_path, pub_path, created = ensure_project_key(project_root)
    except OSError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e
    if created:
        click.echo(f"Generated new Ed25519 keypair for project {project_id}")
    else:
        click.echo(f"Key already exists for project {project_id}")
    click.echo(f"  public key: {pub_path}")


@axiom_group.command("sign")
@click.argument("file", type=click.Path(path_type=Path, exists=True))
@click.option(
    "--key",
    type=click.Path(path_type=Path),
    default=None,
    help="Secret key PEM (default: ~/.omnix/keys/secret.pem)",
)
@click.option(
    "--out",
    "sig_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output signature path (default: FILE.sig)",
)
def cmd_sign(file: Path, key: Path | None, sig_path: Path | None) -> None:
    key = (key or (_DEFAULT_KEY_DIR / "secret.pem")).expanduser()
    out = sig_path or Path(str(file) + ".sig")
    try:
        sk_pem = key.read_text(encoding="ascii")
        sk = keystore.secret_from_pem(sk_pem)
    except (OSError, ValueError) as e:
        click.echo(f"cannot load secret key: {e}", err=True)
        raise SystemExit(1) from e
    try:
        msg = file.read_bytes()
    except OSError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e
    rnd = secrets.token_bytes(32)
    try:
        sig = sign.sign_bytes(sk, msg, b"", rnd)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e
    try:
        out.write_text(keystore.signature_to_pem(sig), encoding="ascii")
    except OSError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from e


@axiom_group.command("verify")
@click.argument("file", type=click.Path(path_type=Path))
@click.argument("sigfile", type=click.Path(path_type=Path))
@click.option(
    "--pubkey",
    "pub_path",
    type=click.Path(path_type=Path, exists=True),
    required=True,
)
def cmd_verify(file: Path, sigfile: Path, pub_path: Path) -> None:
    try:
        pk = keystore.public_from_pem(pub_path.read_text(encoding="ascii"))
        sig = keystore.signature_from_pem(sigfile.read_text(encoding="ascii"))
        msg = file.read_bytes()
    except OSError as e:
        click.echo(str(e), err=True)
        raise SystemExit(2) from e
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(2) from e
    ok = vfy.verify_bytes(pk, msg, b"", sig)
    if ok:
        click.echo("Signature verified successfully")
        raise SystemExit(0)
    click.echo("Signature verification FAILED", err=True)
    raise SystemExit(1)


@axiom_group.command("verify-rebuild")
@click.argument(
    "receipt_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
)
@click.option(
    "--pubkey",
    "pubkey_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Ed25519 public key PEM. If omitted, searches parents for .omnix/pubkey.pem.",
)
@click.option("--json", "as_json", is_flag=True, default=False)
def verify_rebuild_cmd(
    receipt_path: Path,
    pubkey_path: Path | None,
    as_json: bool,
) -> None:
    """Verify a signed M1 rebuild receipt offline (Ed25519).

    Reports verified=true/false plus a summary of gate statuses. Gates
    5+6 marked `deferred_m2` are surfaced explicitly — never silently
    counted as passes.
    """
    from omnix.receipts.rebuild_receipt import RebuildReceipt, verify_rebuild

    receipt_p = receipt_path.expanduser().resolve(strict=True)
    sig_p = receipt_p.with_suffix(".sig")
    if not sig_p.is_file():
        payload = {
            "verified": False,
            "reason": "missing_sig",
            "receipt_path": str(receipt_p),
        }
        if as_json:
            click.echo(json.dumps(payload))
        else:
            click.echo(f"FAIL: missing signature at {sig_p}", err=True)
        raise SystemExit(2)

    pub = pubkey_path
    if pub is None:
        pub = _discover_ed25519_pubkey(receipt_p)
        if pub is None:
            payload = {
                "verified": False,
                "reason": "pubkey_discovery_failed",
                "receipt_path": str(receipt_p),
            }
            if as_json:
                click.echo(json.dumps(payload))
            else:
                click.echo(
                    "FAIL: no Ed25519 pubkey found in parent .omnix/ dirs; "
                    "pass --pubkey explicitly.",
                    err=True,
                )
            raise SystemExit(2)

    try:
        receipt_dict = json.loads(receipt_p.read_text(encoding="utf-8"))
        receipt = RebuildReceipt.from_dict(receipt_dict)
    except (ValueError, json.JSONDecodeError) as exc:
        payload = {
            "verified": False,
            "reason": "malformed_receipt",
            "error": str(exc),
            "receipt_path": str(receipt_p),
        }
        if as_json:
            click.echo(json.dumps(payload))
        else:
            click.echo(f"FAIL: malformed receipt: {exc}", err=True)
        raise SystemExit(2)

    sig_b64 = sig_p.read_text(encoding="utf-8").strip()
    verified = verify_rebuild(receipt, sig_b64, pub)

    statuses: dict[str, int] = {}
    for g in receipt.gate_results:
        statuses[g.status] = statuses.get(g.status, 0) + 1
    gates_summary = "/".join(
        f"{statuses.get(s, 0)}-{s}"
        for s in ("passed", "failed", "skipped", "deferred_m2")
    )

    payload = {
        "verified": verified,
        "reason": None if verified else "signature_mismatch",
        "receipt_path": str(receipt_p),
        "node_fqn": receipt.node_fqn,
        "model": receipt.model,
        "target_language": receipt.target_language,
        "gates_summary": gates_summary,
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        line = "verified" if verified else "FAILED"
        click.echo(f"{line}: {receipt.node_fqn} ({receipt.model})")
        click.echo(f"  gates_summary: {gates_summary}")
    raise SystemExit(0 if verified else 1)


@axiom_group.command("verify-finding")
@click.argument(
    "receipt_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
)
@click.option(
    "--pubkey",
    "pubkey_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Ed25519 public key PEM. If omitted, searches parents for .omnix/pubkey.pem.",
)
@click.option("--json", "as_json", is_flag=True, default=False)
def verify_finding_cmd(
    receipt_path: Path,
    pubkey_path: Path | None,
    as_json: bool,
) -> None:
    """Verify a single signed finding receipt (Ed25519)."""
    from .finding_keys import verify_finding

    receipt_p = receipt_path.expanduser().resolve(strict=True)
    sig_p = receipt_p.with_suffix(".sig")
    if not sig_p.is_file():
        payload = {
            "verified": False,
            "reason": "missing_sig",
            "receipt_path": str(receipt_p),
        }
        if as_json:
            click.echo(json.dumps(payload))
        else:
            click.echo(f"FAIL: missing signature at {sig_p}", err=True)
        raise SystemExit(2)

    pub = pubkey_path
    if pub is None:
        pub = _discover_ed25519_pubkey(receipt_p)
        if pub is None:
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "verified": False,
                            "reason": "pubkey_discovery_failed",
                            "receipt_path": str(receipt_p),
                        }
                    )
                )
            else:
                click.echo(
                    "no --pubkey given and auto-discovery failed "
                    "(no .omnix/pubkey.pem in parents)",
                    err=True,
                )
            raise SystemExit(2)
    else:
        pub = pub.expanduser().resolve(strict=True)

    try:
        receipt_dict = json.loads(receipt_p.read_text(encoding="utf-8"))
        sig_str = sig_p.read_text(encoding="ascii").strip()
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "verified": False,
                        "reason": "read_error",
                        "receipt_path": str(receipt_p),
                        "detail": str(e),
                    }
                )
            )
        else:
            click.echo(f"internal error: {e}", err=True)
        raise SystemExit(3) from e

    try:
        ok = verify_finding(receipt_dict, sig_str, pub)
    except FileNotFoundError as e:
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "verified": False,
                        "reason": "missing_pubkey",
                        "receipt_path": str(receipt_p),
                        "detail": str(e),
                    }
                )
            )
        else:
            click.echo(str(e), err=True)
        raise SystemExit(2) from e
    except Exception as e:  # noqa: BLE001 — CLI boundary
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "verified": False,
                        "reason": "internal_error",
                        "receipt_path": str(receipt_p),
                        "detail": str(e),
                    }
                )
            )
        else:
            click.echo(f"internal error: {e}", err=True)
        raise SystemExit(3) from e

    if as_json:
        click.echo(
            json.dumps(
                {
                    "verified": ok,
                    "reason": "ok" if ok else "signature_invalid",
                    "receipt_path": str(receipt_p),
                }
            )
        )
    elif ok:
        click.echo("verified")
    else:
        click.echo("FAIL: signature invalid (Ed25519)", err=True)
    raise SystemExit(0 if ok else 1)


@axiom_group.command("verify-scan")
@click.argument(
    "scan_dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.option(
    "--ed25519-pubkey",
    "ed_pubkey",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Ed25519 project pubkey PEM. Default: discover .omnix/pubkey.pem from parents.",
)
@click.option(
    "--mldsa-pubkey",
    "mldsa_pubkey",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="ML-DSA public PEM for manifest. Default: ~/.omnix/keys/public.pem",
)
@click.option("--json", "as_json", is_flag=True, default=False)
def verify_scan_cmd(
    scan_dir: Path,
    ed_pubkey: Path | None,
    mldsa_pubkey: Path | None,
    as_json: bool,
) -> None:
    """Verify a scan directory (ML-DSA manifest + per-finding Ed25519 + Merkle root)."""
    from omnix.find_bugs.receipt_emitter import verify_scan_directory

    sd = scan_dir.expanduser().resolve(strict=True)

    ed = ed_pubkey.expanduser().resolve(strict=True) if ed_pubkey else _discover_ed25519_pubkey(sd)
    if ed is None or not ed.is_file():
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "verified": False,
                        "reason": "missing_ed25519_pubkey",
                        "scan_dir": str(sd),
                        "finding_count": 0,
                        "manifest_summary": {},
                    }
                )
            )
        else:
            click.echo(
                "missing Ed25519 pubkey (--ed25519-pubkey or auto-discovery failed)",
                err=True,
            )
        raise SystemExit(2)

    mldsa = (
        mldsa_pubkey.expanduser().resolve(strict=True)
        if mldsa_pubkey
        else _DEFAULT_MLDSA_PUB.expanduser().resolve()
    )
    if not mldsa.is_file():
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "verified": False,
                        "reason": "missing_mldsa_pubkey",
                        "scan_dir": str(sd),
                        "finding_count": 0,
                        "manifest_summary": {},
                    }
                )
            )
        else:
            click.echo(f"missing ML-DSA pubkey at {mldsa}", err=True)
        raise SystemExit(2)

    finding_count, manifest_summary = _manifest_scan_summary(sd)

    try:
        ok, reason = verify_scan_directory(sd, ed, mldsa)
    except Exception as e:  # noqa: BLE001
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "verified": False,
                        "reason": "internal_error",
                        "scan_dir": str(sd),
                        "finding_count": finding_count,
                        "manifest_summary": manifest_summary,
                        "detail": str(e),
                    }
                )
            )
        else:
            click.echo(f"internal error: {e}", err=True)
        raise SystemExit(3) from e

    if as_json:
        click.echo(
            json.dumps(
                {
                    "verified": ok,
                    "reason": reason,
                    "scan_dir": str(sd),
                    "finding_count": finding_count,
                    "manifest_summary": manifest_summary,
                }
            )
        )
    elif ok:
        click.echo(f"verified  finding_count={finding_count}")
    else:
        click.echo(f"FAIL: {reason}", err=True)
    raise SystemExit(0 if ok else 1)


@axiom_group.command("export-vault")
@click.argument(
    "project_path",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.option(
    "--since",
    "since_iso",
    type=str,
    default=None,
    help="Include only scans with scan_started_at >= this ISO 8601 string.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output zip path (default: ./omnix-vault-<project_id>-<timestamp>.zip).",
)
@click.option(
    "--include-tampered",
    is_flag=True,
    default=False,
    help="Include scans that fail verify_scan_directory (default: exclude with warning).",
)
def export_vault_cmd(
    project_path: Path,
    since_iso: str | None,
    out_path: Path | None,
    include_tampered: bool,
) -> None:
    """Zip verified finding scans + public keys + README for auditor handoff."""
    from .export_vault import build_vault_zip

    root = project_path.expanduser().resolve(strict=True)
    try:
        dest, n_inc, n_exc = build_vault_zip(
            root,
            out_path.expanduser().resolve() if out_path else None,
            since_iso=since_iso,
            include_tampered=include_tampered,
        )
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        msg = str(e).lower()
        if "no scans" in msg or "no verifiable" in msg or "matching --since" in msg:
            raise SystemExit(1) from e
        raise SystemExit(2) from e
    except OSError as e:
        click.echo(str(e), err=True)
        raise SystemExit(2) from e

    click.echo(f"wrote {dest}  ({n_inc} scans included, {n_exc} excluded as tampered)")
    raise SystemExit(0)
