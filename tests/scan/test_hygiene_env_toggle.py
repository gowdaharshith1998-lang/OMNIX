"""Regression: forkserver env cleanup on hygiene toggle (codex adversarial).

Two findings from the codex adversarial review of phase C:
  * HIGH — `_run_verify_limited` set hygiene env keys via `subprocess_env_overrides`
    but never cleared stale ones. On Python 3.14 forkserver, a worker can hold
    an env snapshot from a prior hygiene-enabled scan; running a hygiene-disabled
    scan in the same process would let the stale REPO_ROOT/STRICT/etc. leak in.
  * MEDIUM — `_child_verify` (Hypothesis-import fallback path) did not apply
    `subprocess_env_overrides` at all, so the override mechanism evaporated
    when the fallback fired.

Both fixes are symmetric: when this run does NOT enable hygiene
(`OMNIX_FS_HYGIENE_ENABLED` absent from overrides), pop all `OMNIX_FS_HYGIENE_*`
keys from the env we are about to apply, then apply whatever overrides remain.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from omnix.find_bugs import runner as fb_runner


_HYGIENE_KEYS = (
    "OMNIX_FS_HYGIENE_ENABLED",
    "OMNIX_FS_HYGIENE_REPO_ROOT",
    "OMNIX_FS_HYGIENE_HYPOTHESIS_DIR",
    "OMNIX_FS_HYGIENE_VERIFY_WS",
    "OMNIX_FS_HYGIENE_STRICT",
    "OMNIX_FS_HYGIENE_REPRO_CMD",
)


class _FakePopen:
    """Captures env passed to subprocess.Popen without spawning a process."""

    last_env: dict[str, str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _FakePopen.last_env = dict(kwargs.get("env") or {})
        # Minimal stdin/stdout shape so caller's `.communicate` / `.poll` don't crash.

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        return (b"{}", b"")

    def poll(self) -> int | None:
        return 0

    @property
    def returncode(self) -> int:
        return 0

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _run_args(*, hygiene_keys: dict[str, str] | None, repo_root: Path) -> dict[str, Any]:
    """Build a minimal run_args dict that `_run_verify_limited` accepts."""
    overrides: dict[str, str] = dict(hygiene_keys) if hygiene_keys else {}
    return {
        "target_path": str(repo_root / "fixture.py"),
        "examples": 1,
        "graph_db_path": str(repo_root / "graph.db"),
        "codebase_root": str(repo_root),
        "omnix_root": str(repo_root),
        "hypothesis_database_directory": str(repo_root / "hyp"),
        "verify_workspace_dir": str(repo_root / "ws"),
        "max_shrink_seconds": 1,
        "rss_cap_bytes": 64 * 1024 * 1024,
        "per_fn_timeout_s": 5.0,
        "subprocess_env_overrides": overrides,
    }


def test_run_verify_limited_toggle_clears_stale_hygiene_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Toggle pattern: hygiene-enabled scan, then hygiene-disabled scan.

    The second call's env handed to subprocess.Popen must not contain any
    stale OMNIX_FS_HYGIENE_* keys from the first.
    """
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    # Pretend a prior call already polluted the parent's os.environ — exactly
    # the forkserver-stale shape codex flagged.
    for k in _HYGIENE_KEYS:
        monkeypatch.setenv(k, f"stale-{k}")

    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()

    # First call: hygiene enabled for repo_a.
    args_enabled = _run_args(
        hygiene_keys={
            "OMNIX_FS_HYGIENE_ENABLED": "1",
            "OMNIX_FS_HYGIENE_REPO_ROOT": str(repo_a.resolve()),
            "OMNIX_FS_HYGIENE_STRICT": "0",
        },
        repo_root=repo_a,
    )
    fb_runner._run_verify_limited(args_enabled, timeout_s=5.0)
    first_env = _FakePopen.last_env or {}
    assert first_env.get("OMNIX_FS_HYGIENE_ENABLED") == "1"
    assert first_env.get("OMNIX_FS_HYGIENE_REPO_ROOT") == str(repo_a.resolve())

    # Second call: hygiene disabled for repo_b in the SAME parent process.
    args_disabled = _run_args(hygiene_keys=None, repo_root=repo_b)
    fb_runner._run_verify_limited(args_disabled, timeout_s=5.0)
    second_env = _FakePopen.last_env or {}

    # The fix: stale hygiene keys from the prior parent os.environ must be
    # popped, even though subprocess_env_overrides for this call is empty.
    for k in _HYGIENE_KEYS:
        assert k not in second_env, (
            f"stale {k}={second_env.get(k)!r} leaked into hygiene-disabled scan "
            f"(forkserver staleness regression — see codex adversarial finding)"
        )


def test_child_verify_applies_overrides_and_clears_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_child_verify` (Hypothesis fallback path) mirrors `_run_verify_limited`.

    Codex MEDIUM finding: the fallback path dropped `subprocess_env_overrides`
    entirely, reintroducing the staleness bug. Fix: apply the same override +
    pop-stale logic on os.environ inside the child.
    """

    # Stub out the actual verify call so we only test env mutation.
    def _fake_run(*_args: Any, **_kwargs: Any) -> tuple[int, str]:
        return (0, "{}")

    monkeypatch.setattr(fb_runner.verify_runner, "run", _fake_run)

    class _Q:
        def __init__(self) -> None:
            self.items: list[Any] = []

        def put(self, item: Any) -> None:
            self.items.append(item)

    # Pollute os.environ as if a prior hygiene-enabled run snapshot lingered.
    for k in _HYGIENE_KEYS:
        monkeypatch.setenv(k, f"stale-{k}")

    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    args = _run_args(hygiene_keys=None, repo_root=repo_b)
    args["target_path"] = str(repo_b / "fixture.py")

    fb_runner._child_verify(_Q(), args)

    for k in _HYGIENE_KEYS:
        assert k not in os.environ, (
            f"stale {k} survived _child_verify with hygiene disabled "
            f"(Hypothesis-fallback override regression — see codex adversarial finding)"
        )


def test_child_verify_applies_overrides_when_hygiene_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When hygiene IS enabled, `_child_verify` must propagate the overrides
    onto os.environ (not just drop the dict)."""

    monkeypatch.setattr(
        fb_runner.verify_runner, "run", lambda *_a, **_k: (0, "{}")
    )

    class _Q:
        def put(self, _item: Any) -> None:
            return None

    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()

    # Start with a clean slate.
    for k in _HYGIENE_KEYS:
        monkeypatch.delenv(k, raising=False)

    args = _run_args(
        hygiene_keys={
            "OMNIX_FS_HYGIENE_ENABLED": "1",
            "OMNIX_FS_HYGIENE_REPO_ROOT": str(repo_a.resolve()),
            "OMNIX_FS_HYGIENE_STRICT": "1",
        },
        repo_root=repo_a,
    )
    fb_runner._child_verify(_Q(), args)

    assert os.environ.get("OMNIX_FS_HYGIENE_ENABLED") == "1"
    assert os.environ.get("OMNIX_FS_HYGIENE_REPO_ROOT") == str(repo_a.resolve())
    assert os.environ.get("OMNIX_FS_HYGIENE_STRICT") == "1"
