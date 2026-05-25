"""Tests for the ``omnix scan`` CLI verb."""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from omnix.cli_scan import _classify, scan_cmd


# ----- classification -----


def test_classify_local(tmp_path):
    (tmp_path / "src").mkdir()
    assert _classify(str(tmp_path / "src")) == "local"


def test_classify_tarball_targz(tmp_path):
    p = tmp_path / "x.tar.gz"
    p.write_bytes(b"\x1f\x8b")  # gzip magic — file just needs to exist
    assert _classify(str(p)) == "tarball"


def test_classify_tarball_tgz(tmp_path):
    p = tmp_path / "y.tgz"
    p.write_bytes(b"\x1f\x8b")
    assert _classify(str(p)) == "tarball"


def test_classify_tarball_plain_tar(tmp_path):
    p = tmp_path / "z.tar"
    p.write_bytes(b"")
    assert _classify(str(p)) == "tarball"


def test_classify_git_https():
    assert _classify("https://github.com/example/repo") == "git"


def test_classify_git_http():
    assert _classify("http://gitea.internal/example/repo.git") == "git"


def test_classify_git_ssh():
    assert _classify("git@github.com:example/repo.git") == "git"
    assert _classify("ssh://git@host/example/repo") == "git"


def test_classify_unknown_raises(tmp_path):
    with pytest.raises(Exception):
        _classify(str(tmp_path / "does-not-exist"))


# ----- end-to-end CLI invocation with mocked httpx -----


def test_scan_local_no_wait_dispatch(tmp_path, monkeypatch):
    """``omnix scan ./src --no-wait`` should:
    - classify as local
    - tar locally + tus create + tus patch
    - POST /v1/jobs
    - persist job-created.json and exit 0 without polling.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("print('hi')")

    seen: list[tuple[str, str]] = []

    def fake_post(self, url, *a, **kw):
        seen.append(("POST", url))
        if url.endswith("/v1/upload/"):
            return httpx.Response(
                201,
                headers={"Location": "/v1/upload/up-1"},
                request=httpx.Request("POST", url),
            )
        if url.endswith("/v1/jobs"):
            return httpx.Response(
                202,
                json={"job_id": "job-1", "state": "queued"},
                request=httpx.Request("POST", url),
            )
        raise AssertionError(f"unexpected POST {url}")

    def fake_patch(self, url, *a, **kw):
        seen.append(("PATCH", url))
        return httpx.Response(204, request=httpx.Request("PATCH", url))

    def fake_get(self, url, *a, **kw):
        seen.append(("GET", url))
        if "/v1/upload/" in url and url.endswith("/status"):
            return httpx.Response(
                200,
                json={"storage_key": "uploads/anonymous/up-1/scan.tar.gz"},
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "patch", fake_patch)
    monkeypatch.setattr(httpx.Client, "get", fake_get)

    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        scan_cmd,
        [str(src), "--no-wait", "--output", str(out), "--endpoint", "http://api"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "job-created.json").exists()
    saved = json.loads((out / "job-created.json").read_text())
    assert saved["job_id"] == "job-1"
    # Confirm we actually went through upload + status + jobs in that order
    methods = [m for m, _ in seen]
    assert methods.count("POST") == 2  # /v1/upload/ + /v1/jobs
    assert methods.count("PATCH") == 1
    # The status GET is best-effort (storage_key resolution)
    assert any(url.endswith("/status") for _, url in seen)


def test_scan_tarball_no_wait_dispatch(tmp_path, monkeypatch):
    """Passing a .tar.gz file directly skips the tar-locally step."""
    tarball = tmp_path / "code.tar.gz"
    tarball.write_bytes(b"\x1f\x8bfake")

    seen: list[tuple[str, str]] = []

    def fake_post(self, url, *a, **kw):
        seen.append(("POST", url))
        if url.endswith("/v1/upload/"):
            return httpx.Response(
                201,
                headers={"location": "/v1/upload/up-2"},  # lowercase header
                request=httpx.Request("POST", url),
            )
        if url.endswith("/v1/jobs"):
            return httpx.Response(
                202,
                json={"job_id": "job-2", "state": "queued"},
                request=httpx.Request("POST", url),
            )
        raise AssertionError(f"unexpected POST {url}")

    def fake_patch(self, url, *a, **kw):
        seen.append(("PATCH", url))
        return httpx.Response(204, request=httpx.Request("PATCH", url))

    def fake_get(self, url, *a, **kw):
        if url.endswith("/status"):
            return httpx.Response(
                200,
                json={"storage_key": "uploads/anonymous/up-2/code.tar.gz"},
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(httpx.Client, "patch", fake_patch)
    monkeypatch.setattr(httpx.Client, "get", fake_get)

    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        scan_cmd,
        [str(tarball), "--no-wait", "--output", str(out), "--endpoint", "http://api"],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads((out / "job-created.json").read_text())
    assert saved["job_id"] == "job-2"


def test_scan_git_url_no_wait_dispatch(tmp_path, monkeypatch):
    """Git URL form posts to /v1/git/clone; if no job_id returned, falls through
    to /v1/jobs with type=git source."""

    def fake_post(self, url, *a, **kw):
        if url.endswith("/v1/git/clone"):
            return httpx.Response(
                200,
                json={"job_id": "job-git-1", "state": "queued"},
                request=httpx.Request("POST", url),
            )
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        scan_cmd,
        [
            "https://github.com/example/repo.git",
            "--no-wait",
            "--output",
            str(out),
            "--endpoint",
            "http://api",
        ],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads((out / "job-created.json").read_text())
    assert saved["job_id"] == "job-git-1"


def test_scan_help_shows_examples():
    """Confirm the --help text mentions all three forms."""
    runner = CliRunner()
    result = runner.invoke(scan_cmd, ["--help"])
    assert result.exit_code == 0
    for marker in ("./my-app", "https://github.com", ".tar.gz"):
        assert marker in result.output, f"--help missing example: {marker}"
