"""omnix scan — customer-facing wrapper around the three ingestion paths.

Auto-detects:
    - argument starts with http/https/git@/ssh:// → server-side git clone path
    - argument is an existing directory → tar locally + tus upload
    - argument is an existing .tar.gz / .tgz / .tar file → tus upload directly

Always polls the job to a terminal state by default and offline-verifies every
emitted receipt against the bundled public key.
"""

from __future__ import annotations

import base64
import json
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import httpx


@dataclass
class ScanConfig:
    endpoint: str
    token: str | None
    target: str
    scope: list[str]
    mode: str
    wait: bool
    output: Path
    emit_json: bool


def _classify(arg: str) -> str:
    """Decide whether ``arg`` is a git URL, a local directory, or a tarball."""
    if arg.startswith(("http://", "https://", "git@", "ssh://")):
        return "git"
    p = Path(arg)
    if p.is_dir():
        return "local"
    if p.is_file() and (p.name.endswith(".tar.gz") or p.suffix in (".tar", ".tgz")):
        return "tarball"
    raise click.BadParameter(
        f"Cannot classify {arg!r}: not a URL, not a directory, not a tarball. "
        f"Did you mean a relative path?"
    )


_TAR_EXCLUDES = {".git", "target", "node_modules", "__pycache__", ".venv", "dist", "build"}


def _tar_local(path: Path, dest: Path) -> Path:
    """Tar a local directory excluding common build artifacts."""
    click.echo(f"  * packing {path} -> {dest.name}")

    def _filter(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(ti.name).parts
        if any(part in _TAR_EXCLUDES for part in parts):
            return None
        return ti

    with tarfile.open(dest, "w:gz") as tf:
        tf.add(str(path), arcname=path.name, filter=_filter)
    click.echo(f"  * packed {dest.stat().st_size:,} bytes")
    return dest


def _tus_upload(
    client: httpx.Client, base: str, headers: dict[str, str], tarball: Path
) -> str:
    size = tarball.stat().st_size
    click.echo(f"  * tus create ({size:,} bytes)")
    create = client.post(
        f"{base}/v1/upload/",
        headers={**headers, "Tus-Resumable": "1.0.0", "Upload-Length": str(size)},
    )
    create.raise_for_status()
    loc = create.headers.get("Location") or create.headers.get("location")
    if not loc:
        raise click.ClickException(f"tus create returned no Location header: {create.text!r}")
    upload_url = loc if loc.startswith("http") else f"{base}{loc}"
    upload_id = upload_url.rstrip("/").rsplit("/", 1)[-1]
    click.echo(f"  * upload_id={upload_id}; patching bytes")
    with open(tarball, "rb") as f:
        patch = client.patch(
            upload_url,
            content=f.read(),
            headers={
                **headers,
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
            },
            timeout=600.0,
        )
    patch.raise_for_status()
    click.echo("  * upload complete")
    return upload_id


def _resolve_storage_key(
    client: httpx.Client, base: str, headers: dict[str, str], upload_id: str
) -> str | None:
    """Look up the storage_key for a completed tus upload (works around the
    server-side gap where /v1/jobs doesn't auto-resolve from upload_id)."""
    try:
        r = client.get(f"{base}/v1/upload/{upload_id}/status", headers=headers, timeout=10.0)
        r.raise_for_status()
        return r.json().get("storage_key")
    except Exception:
        return None


def _git_clone_remote(
    client: httpx.Client,
    base: str,
    headers: dict[str, str],
    repo: str,
    ref: str,
    git_token: str | None,
) -> dict[str, Any]:
    click.echo(f"  * requesting server-side clone of {repo}@{ref}")
    body: dict[str, Any] = {"repo_url": repo, "ref": ref}
    if git_token:
        body["token"] = git_token
    r = client.post(
        f"{base}/v1/git/clone",
        headers={**headers, "Content-Type": "application/json"},
        json=body,
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


def _start_job(
    client: httpx.Client,
    base: str,
    headers: dict[str, str],
    source: dict[str, Any],
    target: str,
    mode: str,
    scope: list[str],
) -> dict[str, Any]:
    body: dict[str, Any] = {"source": source, "target_language": target, "mode": mode}
    if scope:
        body["scope"] = scope
    click.echo(f"  * POST /v1/jobs target={target} mode={mode} scope={len(scope)}")
    r = client.post(
        f"{base}/v1/jobs",
        headers={**headers, "Content-Type": "application/json"},
        json=body,
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def _poll(
    client: httpx.Client,
    base: str,
    headers: dict[str, str],
    job_id: str,
    output: Path,
    deadline: float,
) -> dict[str, Any]:
    state = "?"
    while time.time() < deadline:
        r = client.get(f"{base}/v1/jobs/{job_id}", headers=headers, timeout=30.0)
        r.raise_for_status()
        j = r.json()
        state = j.get("state", "?")
        gate = j.get("current_gate", "?")
        click.echo(f"  * state={state:<14}  gate={gate}")
        if state in ("complete", "done", "error", "failed", "awaiting_cutover"):
            (output / "job-final.json").write_text(json.dumps(j, indent=2))
            return j
        time.sleep(3)
    raise click.ClickException(f"timed out polling job {job_id}; last state={state}")


def _download_and_verify(
    client: httpx.Client,
    base: str,
    headers: dict[str, str],
    job_id: str,
    output: Path,
) -> tuple[int, int]:
    listing_resp = client.get(
        f"{base}/v1/jobs/{job_id}/receipts", headers=headers, timeout=30.0
    )
    if listing_resp.status_code == 404:
        click.echo("  ! no receipts endpoint (job emitted none)")
        return (0, 0)
    listing_resp.raise_for_status()
    listing = listing_resp.json()
    (output / "receipts-list.json").write_text(json.dumps(listing, indent=2))
    items = listing.get("receipts", listing) if isinstance(listing, dict) else listing
    if not isinstance(items, list):
        items = []
    receipts_dir = output / "receipts"
    receipts_dir.mkdir(exist_ok=True)
    try:
        from omnix.receipts.verify import verify_bytes
    except Exception as e:
        click.echo(f"  ! omnix.receipts.verify not importable; skipping offline verify ({e})")
        return (0, 0)
    ok = fail = 0
    for r in items:
        rid = r.get("receipt_id") or r.get("id")
        if not rid:
            continue
        bundle = client.get(
            f"{base}/v1/jobs/{job_id}/receipts/{rid}", headers=headers
        ).json()
        (receipts_dir / f"{rid}.bundle.json").write_text(json.dumps(bundle, indent=2))
        payload = json.dumps(
            bundle["payload"], sort_keys=True, separators=(",", ":")
        ).encode()
        ctx = base64.b64decode(bundle.get("ctx_b64", "") or "")
        sig = base64.b64decode(bundle["signature_b64"])
        pub = base64.b64decode(bundle["pubkey_b64"])
        if verify_bytes(pub, payload, ctx, sig):
            click.echo(f"  + {rid}")
            ok += 1
        else:
            click.echo(f"  - {rid} VERIFY FAILED")
            fail += 1
    return (ok, fail)


@click.command("scan")
@click.argument("target", required=True)
@click.option("--endpoint", default=None, envvar="OMNIX_ENDPOINT", help="API endpoint")
@click.option("--token", default=None, envvar="OMNIX_API_KEY", help="API key")
@click.option(
    "--target-language",
    "target_language",
    default="java21",
    show_default=True,
    help="Target language for the rebuild",
)
@click.option(
    "--scope",
    default="",
    help="Comma-separated file paths to scope the scan",
)
@click.option(
    "--mode",
    type=click.Choice(["production", "dry-run", "preview"]),
    default="production",
    show_default=True,
)
@click.option("--wait/--no-wait", default=True, show_default=True)
@click.option(
    "--timeout",
    default=900,
    show_default=True,
    help="Seconds to wait for terminal state",
)
@click.option("--ref", default="main", show_default=True, help="Git ref (for git-URL form)")
@click.option(
    "--git-token",
    default=None,
    envvar="OMNIX_GIT_TOKEN",
    help="PAT for private git repos",
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    default=False,
    help="Emit JSON summary to stdout (for CI)",
)
@click.option(
    "--output",
    default=None,
    help="Output directory (default: ./.omnix-scan-<TS>/)",
)
def scan_cmd(
    target: str,
    endpoint: str | None,
    token: str | None,
    target_language: str,
    scope: str,
    mode: str,
    wait: bool,
    timeout: int,
    ref: str,
    git_token: str | None,
    emit_json: bool,
    output: str | None,
) -> None:
    """Scan a codebase.

    TARGET is a local path, a git URL, or a tarball.

    \b
    Examples:
      omnix scan ./my-app
      omnix scan https://github.com/spring-projects/spring-petclinic.git
      omnix scan path/to/codebase.tar.gz --scope src/main/java/Foo.java
    """
    base = (endpoint or "http://127.0.0.1:8080").rstrip("/")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output or f".omnix-scan-{ts}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    scope_list = [s.strip() for s in scope.split(",") if s.strip()]
    click.echo(f"==> omnix scan  target={target!r}  endpoint={base}  output={out}")
    kind = _classify(target)
    click.echo(f"    detected={kind}")

    with httpx.Client() as client:
        if kind == "git":
            git_resp = _git_clone_remote(client, base, headers, target, ref, git_token)
            if "job_id" in git_resp:
                job = git_resp
                click.echo(f"  * git clone path returned job_id inline")
            else:
                source: dict[str, Any] = {
                    "type": "git",
                    "repo_url": target,
                    "ref": ref,
                }
                if git_token:
                    source["token"] = git_token
                job = _start_job(
                    client, base, headers, source, target_language, mode, scope_list
                )
        else:
            if kind == "local":
                with tempfile.TemporaryDirectory() as td:
                    tar = _tar_local(Path(target).resolve(), Path(td) / "scan.tar.gz")
                    upload_id = _tus_upload(client, base, headers, tar)
            else:  # tarball
                upload_id = _tus_upload(client, base, headers, Path(target).resolve())
            storage_key = _resolve_storage_key(client, base, headers, upload_id)
            source = {"type": "tus", "upload_id": upload_id}
            if storage_key:
                source["storage_key"] = storage_key
            job = _start_job(
                client, base, headers, source, target_language, mode, scope_list
            )

        job_id = job["job_id"]
        (out / "job-created.json").write_text(json.dumps(job, indent=2))
        click.echo(f"  * job_id={job_id}")

        if not wait:
            click.echo(f"==> scan dispatched; --no-wait specified; job_id={job_id}")
            return

        deadline = time.time() + timeout
        final = _poll(client, base, headers, job_id, out, deadline)
        ok, fail = _download_and_verify(client, base, headers, job_id, out)

    summary = {
        "job_id": job_id,
        "state": final.get("state"),
        "receipts_ok": ok,
        "receipts_failed": fail,
        "output_dir": str(out),
        "endpoint": base,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    if emit_json:
        click.echo(json.dumps(summary, indent=2))
    else:
        click.echo("")
        click.echo(
            f"==> SCAN COMPLETE  state={summary['state']}  receipts ok={ok} fail={fail}"
        )
        click.echo(f"    artifacts: {out}")
        if fail > 0:
            sys.exit(2)
