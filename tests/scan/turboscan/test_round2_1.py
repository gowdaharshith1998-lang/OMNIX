"""Slice 17b round 2.1 — forkserver + calibration + inlined generators (R2.1.x)."""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

import pytest

from omnix.scan.turboscan.calibration import CalibrationReport, calibrate_hot_generators
from omnix.scan.turboscan.inlined_generators import INLINED_REGISTRY
from omnix.scan.turboscan.worker_pool import build_pool, resolve_mp_start_method


def test_R2_1_1_no_fork_deprecation_warnings(tmp_path: Path) -> None:
    """R2.1.1: building the pool produces ZERO fork-related deprecation warnings."""
    with warnings.catch_warnings(record=True) as wrec:
        warnings.simplefilter("always")
        pool = build_pool(4, sandbox_dir=tmp_path)
        pool.apply(_noop)
        pool.close()
        pool.join()
        mgr = getattr(pool, "_omnix_mgr", None)
        if mgr is not None:
            mgr.shutdown()

    fork_warnings = [
        w
        for w in wrec
        if "fork()" in str(w.message).lower()
        or (w.filename and "popen_fork" in w.filename)
    ]
    assert len(fork_warnings) == 0, (
        f"Expected zero fork deprecation warnings, got {len(fork_warnings)}: "
        f"{[str(x.message) for x in fork_warnings]}"
    )


def _noop() -> int:
    return 42


def test_R2_1_2_forkserver_preload_reduces_worker_startup(tmp_path: Path) -> None:
    """R2.1.2: pool creation + first task completes within budget for 8 workers."""
    import time

    t0 = time.monotonic()
    pool = build_pool(8, sandbox_dir=tmp_path, preload=True)
    pool.apply(_noop)
    elapsed = time.monotonic() - t0
    pool.close()
    pool.join()
    mgr = getattr(pool, "_omnix_mgr", None)
    if mgr is not None:
        mgr.shutdown()

    assert elapsed < 5.0, f"Pool startup took {elapsed:.2f}s — exceeds 5s budget"


def test_R2_1_3_calibration_emits_top5_report(
    omnix_repo_path: Path, tmp_path: Path
) -> None:
    """R2.1.3: calibration produces CalibrationReport with 5 entries."""
    report = calibrate_hot_generators(omnix_repo_path, cache_dir=tmp_path)

    assert isinstance(report, CalibrationReport)
    assert len(report.top_generators) == 5

    for entry in report.top_generators:
        assert entry.name
        assert entry.cumulative_ms > 0
        assert entry.call_count > 0
        assert entry.avg_per_call_ms > 0


def test_R2_1_4_inlined_generators_semantically_equivalent_for_top5() -> None:
    """R2.1.4: inlined singletons match fresh strategies for deterministic RNG seeds."""
    from hypothesis.internal.conjecture.data import ConjectureData
    from random import Random

    for _name, bundle in INLINED_REGISTRY.items():
        original_strategy = bundle.original
        inlined = bundle.inlined

        for seed in range(1000):
            r_orig = Random(seed)
            r_inl = Random(seed)
            data_orig = ConjectureData(random=r_orig)
            data_inlined = ConjectureData(random=r_inl)

            v_orig = original_strategy.do_draw(data_orig)
            v_inlined = inlined.do_draw(data_inlined)

            assert v_orig == v_inlined, (
                f"Generator '{bundle.name}' diverged at seed {seed}: "
                f"original={v_orig!r}, inlined={v_inlined!r}"
            )


@pytest.mark.skipif(
    os.environ.get("OMNIX_TURBOSCAN_E2E", "").lower() not in ("1", "true", "yes"),
    reason="Set OMNIX_TURBOSCAN_E2E=1 for full-repo R8 timing gate",
)
def test_R2_1_5_full_scan_under_30s_R8_passes(omnix_repo_path: Path) -> None:
    """R2.1.5 / R8: full TURBOSCAN completes in <30s (Hg's laptop gate)."""
    import time

    from omnix.scan.turboscan.orchestrator import scan

    t0 = time.monotonic()
    result = scan(omnix_repo_path, mode="full", workers=8, examples_default=100)
    elapsed = time.monotonic() - t0

    assert elapsed < 30.0, (
        f"TURBOSCAN took {elapsed:.1f}s — exceeds 30s budget (R8 GATE)"
    )
    assert result.scan_completed_successfully


def test_R2_1_7_calibration_budget_breach_logged(
    caplog: pytest.LogCaptureFixture, omnix_repo_path: Path, tmp_path: Path
) -> None:
    """R2.1.7: calibration emits CALIBRATION_BUDGET_BREACH when wildly over budget."""
    caplog.set_level(logging.WARNING)
    calibrate_hot_generators(
        omnix_repo_path,
        cache_dir=tmp_path,
        layer_budgets={"calibration": 0.0},
        iterations_per_strategy=50,
    )
    assert any(
        "CALIBRATION_BUDGET_BREACH" in r.getMessage() for r in caplog.records
    )


def test_linux_py314_defaults_to_forkserver() -> None:
    """Sanity: Linux Python 3.14+ uses forkserver unless overridden."""
    import sys

    os.environ.pop("OMNIX_TURBOSCAN_START_METHOD", None)
    if sys.platform == "linux" and sys.version_info >= (3, 14):
        assert resolve_mp_start_method() == "forkserver"
