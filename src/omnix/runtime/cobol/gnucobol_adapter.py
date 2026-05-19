"""GNUCOBOL compile/run adapter."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from omnix.runtime.cobol.sandbox import run_command


@dataclass(frozen=True)
class ProgramRun:
    stdout: bytes
    stderr: bytes
    returncode: int


@dataclass(frozen=True)
class FileHash:
    path: str
    sha256: str


def compile_cobol(source_path: Path, *, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    exe = out_dir / source_path.stem
    argv = ["cobc", "-x", "-free", str(source_path), "-o", str(exe)]
    try:
        proc = subprocess.run(argv, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("cobc not found in PATH") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace") or "cobc compile failed")
    return exe


def run_cobol(exe_path: Path, *, stdin_bytes: bytes, cwd: Path, timeout_s: float = 10.0) -> ProgramRun:
    proc = run_command([str(exe_path)], cwd=cwd, stdin_bytes=stdin_bytes, timeout_s=timeout_s)
    return ProgramRun(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)


def hash_file(path: Path) -> FileHash:
    b = path.read_bytes()
    return FileHash(path=str(path), sha256=hashlib.sha256(b).hexdigest())
