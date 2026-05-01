"""Layer 3 worker pool (R3)."""

from __future__ import annotations

from multiprocessing import Manager

from scan.turboscan.worker_pool import map_verify_tasks_serial


def test_R3_serial_runs_with_shared_slot_registry() -> None:
    mgr = Manager()
    slots = mgr.dict()
    payloads = [
        {
            "slot": 0,
            "relp": "x.py",
            "fn": "f",
            "lineno": 1,
            "examples": 1,
            "repro": "",
            "run_args": {
                "examples": 1,
                "sign": False,
                "output_format": "json",
                "graph_db_path": "/nonexistent.db",
                "codebase_root": ".",
                "no_receipt": True,
                "omnix_root": ".",
                "hypothesis_database_directory": ".",
                "verify_workspace_dir": ".",
                "target_path": "/nonexistent.py",
                "function": "nope",
                "max_shrink_seconds": 5,
            },
        }
    ]
    try:
        out = map_verify_tasks_serial(payloads, slots)
    finally:
        mgr.shutdown()
    assert len(out) == 1
    assert out[0]["code"] == 2
