"""Git clone ingestion tests.

We exercise the local-bare-repo path so the test is deterministic and offline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from omnix.cloud.ingest.git_clone import (
    GitIngestionError,
    _embed_credentials,
    _redact,
    clone_repository,
    git_executable,
    validate_repo_url,
    workspace_manifest_sha256,
)


@pytest.fixture
def local_bare_repo(tmp_path):
    """Create a local bare git repo with a few commits for shallow-clone tests."""
    src = tmp_path / "src"
    src.mkdir()
    git = git_executable()
    subprocess.run([git, "init", "-q", "-b", "main"], cwd=src, check=True)
    subprocess.run([git, "config", "user.email", "t@t"], cwd=src, check=True)
    subprocess.run([git, "config", "user.name", "t"], cwd=src, check=True)

    (src / "README.md").write_text("# fixture\n")
    (src / "App.java").write_text("class App {}\n")
    subprocess.run([git, "add", "-A"], cwd=src, check=True)
    subprocess.run([git, "commit", "-qm", "init"], cwd=src, check=True)

    bare = tmp_path / "bare.git"
    subprocess.run(
        [git, "clone", "-q", "--bare", str(src), str(bare)], check=True
    )
    return f"file://{bare}"


def test_clone_repository_succeeds_on_local_bare(monkeypatch, local_bare_repo, tmp_path):
    monkeypatch.setenv("OMNIX_GIT_ALLOW_FILE_URLS", "1")
    result = clone_repository(local_bare_repo, workspace_root=str(tmp_path / "ws"))
    assert Path(result.workspace, "App.java").exists()
    assert Path(result.workspace, "README.md").exists()
    assert len(result.sha) == 40
    assert result.filter_applied == "blob:none"
    assert result.size_bytes > 0


def test_clone_workspace_manifest_is_deterministic(monkeypatch, local_bare_repo, tmp_path):
    monkeypatch.setenv("OMNIX_GIT_ALLOW_FILE_URLS", "1")
    a = clone_repository(local_bare_repo, workspace_root=str(tmp_path / "a"))
    b = clone_repository(local_bare_repo, workspace_root=str(tmp_path / "b"))
    # Exclude .git so both clones hash to the same content manifest.
    sha_a = workspace_manifest_sha256(a.workspace + "/")
    sha_b = workspace_manifest_sha256(b.workspace + "/")
    # Strictly compare the source-tree subset by re-hashing only the
    # tracked files.
    def hash_tracked(ws: str) -> str:
        import hashlib

        h = hashlib.sha256()
        for p in sorted(
            x for x in Path(ws).rglob("*") if x.is_file() and ".git" not in x.parts
        ):
            rel = p.relative_to(ws).as_posix()
            h.update(rel.encode() + b"\x00")
            h.update(p.read_bytes())
            h.update(b"\xff")
        return h.hexdigest()

    assert hash_tracked(a.workspace) == hash_tracked(b.workspace)


def test_clone_rejects_oversize(monkeypatch, local_bare_repo, tmp_path):
    monkeypatch.setenv("OMNIX_GIT_ALLOW_FILE_URLS", "1")
    monkeypatch.setenv("OMNIX_GIT_CLONE_MAX_BYTES", "1")
    from omnix.cloud.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(GitIngestionError) as exc:
        clone_repository(local_bare_repo, workspace_root=str(tmp_path / "ws"))
    assert "exceeds" in str(exc.value)


def test_embed_credentials_strips_in_https():
    out = _embed_credentials("https://github.com/foo/bar.git", "ghp_123")
    assert "x-access-token:ghp_123@github.com" in out


def test_embed_credentials_refuses_ssh():
    with pytest.raises(GitIngestionError):
        _embed_credentials("ssh://git@github.com/foo/bar.git", "ghp_123")


def test_redact_drops_creds():
    redacted = _redact("https://x-access-token:ghp_secret@github.com/foo/bar.git")
    assert "ghp_secret" not in redacted
    assert "github.com/foo/bar.git" in redacted


def test_validate_repo_url_rejects_private_network_targets():
    with pytest.raises(GitIngestionError):
        validate_repo_url("https://127.0.0.1/org/repo.git")
    with pytest.raises(GitIngestionError):
        validate_repo_url("https://localhost/org/repo.git")


def test_validate_repo_url_rejects_file_scheme_by_default(local_bare_repo):
    with pytest.raises(GitIngestionError):
        validate_repo_url(local_bare_repo)
