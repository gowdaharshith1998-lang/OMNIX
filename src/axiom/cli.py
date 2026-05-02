# Compliance: P18, P21, P22, P23

"""Click commands: `omnix axiom keygen|sign|verify`."""

from __future__ import annotations

import secrets
from pathlib import Path

import click

from . import keystore, sign, verify as vfy

_DEFAULT_KEY_DIR = Path.home() / ".omnix" / "keys"


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
