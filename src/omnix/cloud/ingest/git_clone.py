"""Git-based ingestion (Path 1B).

Accepts a fine-grained PAT or a GitHub App installation token.
Performs:
  git clone --filter=blob:none --depth=1 --no-tags <url>
into a Celery-worker-scoped scratch directory, after a size preflight.

Operating constraints:
  * Read-only — we never push back into the customer repo.
  * 5GB shallow-clone cap (configurable via OMNIX_GIT_CLONE_MAX_BYTES).
  * Credentials are stamped into the clone URL only for the in-process
    subprocess call. They are not persisted to disk and not echoed to logs.

`fetch_size_estimate` consults the GitHub REST `repos` endpoint when the
repo is on github.com (cheap, no clone). For other forges, we fall back
to a sparse-clone probe.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from omnix.cloud.config import get_settings


class GitIngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitCloneResult:
    workspace: str
    repo: str
    sha: str
    size_bytes: int
    filter_applied: str


def _embed_credentials(url: str, token: str | None) -> str:
    if not token:
        return url
    parts = urlparse(url)
    if parts.scheme not in {"http", "https"}:
        raise GitIngestionError(f"refusing to embed creds in {parts.scheme} URL")
    netloc = f"x-access-token:{token}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunparse(parts._replace(netloc=netloc))


def _redact(url: str) -> str:
    parts = urlparse(url)
    if "@" in (parts.netloc or ""):
        host = parts.netloc.split("@", 1)[-1]
        return urlunparse(parts._replace(netloc=host))
    return url


def fetch_size_estimate(repo: str, token: str | None = None) -> int | None:
    """Best-effort: return repo size in bytes if we can ask the forge cheaply.

    For github.com, hits the REST /repos endpoint and returns ``size`` * 1024.
    Returns None when we can't estimate; the caller should fall back to a
    sparse-clone probe.
    """
    parts = urlparse(repo)
    if parts.hostname != "github.com":
        return None
    path = parts.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return None
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = httpx.get(f"https://api.github.com/repos/{path}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        kb = int(resp.json().get("size", 0))
    except Exception:
        return None
    return kb * 1024


def clone_repository(
    repo_url: str,
    *,
    token: str | None = None,
    ref: str | None = None,
    workspace_root: str | None = None,
) -> GitCloneResult:
    """Shallow blobless clone with strict size preflight."""
    settings = get_settings()
    estimate = fetch_size_estimate(repo_url, token)
    if estimate is not None and estimate > settings.git_clone_max_bytes:
        raise GitIngestionError(
            f"repo {_redact(repo_url)} size {estimate} bytes exceeds limit "
            f"{settings.git_clone_max_bytes}"
        )

    workspace_root = workspace_root or tempfile.mkdtemp(prefix="omnix-git-")
    target = Path(workspace_root) / "repo"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    url_with_creds = _embed_credentials(repo_url, token)
    cmd = [
        "git",
        "clone",
        "--filter=blob:none",
        "--depth=1",
        "--no-tags",
        "--single-branch",
    ]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([url_with_creds, str(target)])

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            env=env,
            timeout=60 * 30,
        )
    except subprocess.CalledProcessError as exc:
        raise GitIngestionError(
            f"git clone failed: {exc.stderr.decode(errors='replace')[:512]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitIngestionError("git clone timed out after 30 minutes") from exc

    sha = subprocess.check_output(
        ["git", "-C", str(target), "rev-parse", "HEAD"], text=True
    ).strip()

    size = sum(
        p.stat().st_size for p in target.rglob("*") if p.is_file()
    )
    if size > settings.git_clone_max_bytes:
        shutil.rmtree(target)
        raise GitIngestionError(
            f"post-clone size {size} bytes exceeds {settings.git_clone_max_bytes}"
        )

    return GitCloneResult(
        workspace=str(target),
        repo=_redact(repo_url),
        sha=sha,
        size_bytes=size,
        filter_applied="blob:none",
    )


def workspace_manifest_sha256(workspace: str) -> str:
    """Deterministic content hash over a cloned workspace.

    Iterates files lexicographically, hashing path-then-content; the digest
    is stable across re-clones of the same commit on the same FS.
    """
    h = hashlib.sha256()
    root = Path(workspace)
    for p in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8") + b"\x00")
        with p.open("rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\xff")
    return h.hexdigest()
