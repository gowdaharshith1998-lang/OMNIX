"""Subprocess sandbox for COBOL execution."""

from __future__ import annotations

import resource
import subprocess
from pathlib import Path


class SandboxTimeoutError(TimeoutError):
    pass


def _limit_resources(cpu_seconds: int, memory_mb: int) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    mem_bytes = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))


def run_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float = 10.0,
    stdin_bytes: bytes = b"",
    cpu_seconds: int = 2,
    memory_mb: int = 256,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd),
            input=stdin_bytes,
            capture_output=True,
            check=False,
            timeout=timeout_s,
            preexec_fn=lambda: _limit_resources(cpu_seconds, memory_mb),
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxTimeoutError(str(exc)) from exc
