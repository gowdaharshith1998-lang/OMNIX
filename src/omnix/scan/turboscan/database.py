"""Hypothesis DB paths for TURBOSCAN (Layer 5 / R3 / R5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from omnix.scan.turboscan.types import turboscan_state_dir


def worker_hypothesis_dir(repo_root: Path, worker_slot: int) -> Path:
    d = turboscan_state_dir(repo_root) / "workers" / str(int(worker_slot)) / "hypothesis"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def shared_examples_db_dir(repo_root: Path) -> Path:
    """Persistent examples DB root for replay (R5)."""
    d = turboscan_state_dir(repo_root) / "db"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def function_db_subdir(repo_root: Path, relpath: str, function_name: str) -> Path:
    h = hashlib.sha256(f"{relpath}\0{function_name}".encode()).hexdigest()[:16]
    p = shared_examples_db_dir(repo_root) / h
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()
