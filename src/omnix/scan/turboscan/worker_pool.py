"""Layer 3: multiprocessing worker pool with isolated Hypothesis dirs (R3)."""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import time
from multiprocessing import Manager, get_context
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("omnix.scan.turboscan.pool")

_SLOT_BOOK: Any = None

# Heavy imports used by every verify worker — preload before forkserver workers fork.
_FORKSERVER_PRELOAD_MODULES: list[str] = [
    "hypothesis",
    "omnix.find_bugs.runner",
    "omnix.verify.runner",
]


def _configure_forkserver_preload() -> None:
    try:
        multiprocessing.set_forkserver_preload(_FORKSERVER_PRELOAD_MODULES)
    except (AttributeError, ValueError, RuntimeError) as e:
        _LOG.debug("forkserver preload skipped: %s", e)


def resolve_mp_start_method() -> str:
    """Pick Pool start method (R2.1.1). Never default to *fork* on Linux Python 3.14+."""
    override = (os.environ.get("OMNIX_TURBOSCAN_START_METHOD") or "").strip().lower()
    if override in ("fork", "forkserver", "spawn"):
        return override
    if sys.platform == "linux" and sys.version_info >= (3, 14):
        return "forkserver"
    return "fork"


def _pool_context_for_method(meth: str, *, preload: bool) -> Any:
    if meth == "forkserver" and preload:
        _configure_forkserver_preload()
    try:
        return get_context(meth)
    except ValueError:
        return get_context("spawn")


def resolve_worker_pool_context(*, preload: bool = True) -> Any:
    """Return a multiprocessing context for verify worker Pools."""
    meth = resolve_mp_start_method()
    if meth == "forkserver":
        try:
            return _pool_context_for_method("forkserver", preload=preload)
        except (ValueError, OSError) as e:
            _LOG.warning(
                "turboscan: forkserver unavailable (%s) — falling back to spawn", e
            )
            return _pool_context_for_method("spawn", preload=False)
    try:
        use_preload = preload and meth != "fork"
        return _pool_context_for_method(meth, preload=use_preload)
    except ValueError:
        return _pool_context_for_method("spawn", preload=False)


def build_pool(
    workers: int,
    sandbox_dir: Path | None = None,
    *,
    preload: bool = True,
    shared_slots: Any | None = None,
) -> Any:
    """Create a Pool + slot registry for tests (R2.1.1 / R2.1.2).

    ``sandbox_dir`` is accepted for API compatibility with benchmarks;
    worker isolation uses per-payload Hypothesis dirs from the orchestrator.
    """
    del sandbox_dir  # reserved for future sandbox pinning
    mgr: Manager | None = None
    slots: Any = shared_slots
    if slots is None:
        mgr = Manager()
        slots = mgr.dict()
    ctx = resolve_worker_pool_context(preload=preload)
    t0 = time.monotonic()
    pool = ctx.Pool(
        max(1, int(workers)), initializer=_pool_init, initargs=(slots,)
    )
    startup_s = time.monotonic() - t0
    _LOG.info(
        "turboscan pool startup %.3fs workers=%d method=%s preload=%s",
        startup_s,
        workers,
        resolve_mp_start_method(),
        preload,
    )
    setattr(pool, "_omnix_mgr", mgr)
    setattr(pool, "_omnix_startup_s", startup_s)
    setattr(pool, "_omnix_slots", slots)
    return pool


def _pool_init(shared_slots: Any) -> None:
    global _SLOT_BOOK
    _SLOT_BOOK = shared_slots


def run_verify_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable top-level worker entry (fork-safe lazy imports)."""
    from omnix.find_bugs.runner import VERIFY_TIMEOUT_S, _run_verify_limited

    slot = int(payload["slot"])
    book = _SLOT_BOOK
    repro = str(payload.get("repro") or "")
    if book is not None:
        book[slot] = {
            "relp": payload["relp"],
            "fn": payload["fn"],
            "lineno": int(payload["lineno"]),
            "repro": repro,
            "mono": time.monotonic_ns(),
        }
    t0 = time.monotonic_ns()
    err: str | None = None
    code, out, werr = 2, "", "worker internal error"
    try:
        code, out, werr = _run_verify_limited(
            payload["run_args"], VERIFY_TIMEOUT_S
        )
    except Exception as e:  # noqa: BLE001
        err = f"{e!s}"
        _LOG.exception("turboscan worker verify failed")
    finally:
        if book is not None:
            book[slot] = {}
    t1 = time.monotonic_ns()
    return {
        "code": int(code),
        "out": str(out or ""),
        "werr": werr,
        "worker_err": err,
        "relp": payload["relp"],
        "fn": payload["fn"],
        "lineno": int(payload["lineno"]),
        "examples": int(payload["examples"]),
        "t0_ns": t0,
        "t1_ns": t1,
        "slot": slot,
    }


def map_verify_tasks(
    workers: int,
    payloads: list[dict[str, Any]],
    *,
    chunksize: int = 1,
    shared_slots: Any | None = None,
    preload: bool = True,
) -> list[dict[str, Any]]:
    """Run payloads across a ``Pool`` with shared slot registry (R3).

    When ``shared_slots`` is provided (e.g. ``Manager().dict()``), the caller
    owns lifecycle / shutdown of the ``Manager``.
    """
    if not payloads:
        return []
    workers = max(1, min(int(workers), len(payloads)))
    ctx = resolve_worker_pool_context(preload=preload)
    mgr: Manager | None = None
    slots: Any = shared_slots
    if slots is None:
        mgr = Manager()
        slots = mgr.dict()
    try:
        with ctx.Pool(workers, initializer=_pool_init, initargs=(slots,)) as pool:
            out = pool.map(run_verify_task, payloads, chunksize=chunksize)
        return list(out)
    finally:
        if mgr is not None:
            mgr.shutdown()


def map_verify_tasks_serial(
    payloads: list[dict[str, Any]],
    shared_slots: Any | None = None,
) -> list[dict[str, Any]]:
    """Single-process path (tests / spawn compatibility).

    Pass the same ``shared_slots`` ``Manager().dict()`` used by Layer 1 hygiene
    so in-flight verify targets correlate with filesystem events (R2).
    """
    _pool_init(shared_slots)
    return [run_verify_task(p) for p in payloads]
