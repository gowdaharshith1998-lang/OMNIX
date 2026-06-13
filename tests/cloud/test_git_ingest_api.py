"""POST /v1/git/clone API surface tests (inline mode, no Celery)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omnix.cloud.api.main import create_app
from omnix.cloud.auth.jwt_session import issue
from omnix.cloud.ingest.git_clone import git_executable


@pytest.fixture
def local_bare_repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    git = git_executable()
    subprocess.run([git, "init", "-q", "-b", "main"], cwd=src, check=True)
    subprocess.run([git, "config", "user.email", "t@t"], cwd=src, check=True)
    subprocess.run([git, "config", "user.name", "t"], cwd=src, check=True)
    (src / "X.java").write_text("class X {}\n")
    subprocess.run([git, "add", "-A"], cwd=src, check=True)
    subprocess.run([git, "commit", "-qm", "init"], cwd=src, check=True)
    bare = tmp_path / "bare.git"
    subprocess.run([git, "clone", "-q", "--bare", str(src), str(bare)], check=True)
    return f"file://{bare}"


def test_git_clone_inline(monkeypatch, local_bare_repo):
    monkeypatch.setenv("OMNIX_GIT_ALLOW_FILE_URLS", "1")
    client = TestClient(create_app())
    token = issue("u-1", "tenant-1", "smb", "u@example.com")
    resp = client.post(
        "/v1/git/clone",
        json={"repo": local_bare_repo, "inline": True},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant-1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sha"] and len(body["sha"]) == 40
    assert body["workspace"]
    assert Path(body["workspace"], "X.java").exists()


def test_git_clone_invalid_repo_returns_400(tmp_path):
    client = TestClient(create_app())
    token = issue("u-1", "tenant-1", "smb", "u@example.com")
    resp = client.post(
        "/v1/git/clone",
        json={"repo": f"file://{tmp_path}/no-such-thing", "inline": True},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant-1"},
    )
    assert resp.status_code == 400


def test_git_clone_requires_session(local_bare_repo):
    client = TestClient(create_app())
    resp = client.post(
        "/v1/git/clone",
        json={"repo": local_bare_repo, "inline": True},
    )
    assert resp.status_code == 401
