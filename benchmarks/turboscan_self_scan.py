#!/usr/bin/env python3
"""Repeatable wall-clock benchmark: legacy vs TURBOSCAN on a codebase root."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Benchmark find_bugs legacy vs TURBOSCAN")
    p.add_argument("codebase", type=Path, help="Repository root")
    p.add_argument("--examples", type=int, default=50)
    args = p.parse_args()
    root = args.codebase.resolve()
    src = Path(__file__).resolve().parent.parent / "src"
    os.environ.setdefault("PYTHONPATH", str(src))
    sys.path.insert(0, str(src))

    from find_bugs.runner import run_find_bugs
    from scan.turboscan.orchestrator import scan as turboscan_scan

    t0 = time.perf_counter()
    run_find_bugs(str(root), examples=args.examples, json_mode=True, no_bundle=True, turboscan=False)
    legacy_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    turboscan_scan(root, mode="full", examples_default=max(args.examples, 100))
    turbo_t = time.perf_counter() - t0

    print(f"legacy_wall_s={legacy_t:.2f} turboscan_wall_s={turbo_t:.2f} speedup={legacy_t / turbo_t:.2f}x")


if __name__ == "__main__":
    main()
