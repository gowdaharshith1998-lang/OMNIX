"""TURBOSCAN Layer 0 — parallel Python verify dispatch + hygiene coordination."""

from __future__ import annotations

import logging
import os
import shlex
import sys
import time
from multiprocessing import Manager
from pathlib import Path
from typing import Any

from omnix.scan.filesystem_hygiene import (
    load_sandbox_config_from_env,
    parse_bool_env,
    validated_sandbox_roots,
)
from omnix.scan.turboscan.budget_planner import build_budget_plan
from omnix.scan.turboscan.database import worker_hypothesis_dir
from omnix.scan.turboscan.hygiene_inotify import start_hygiene_watcher
from omnix.scan.turboscan.types import BudgetPlan, TurboScanResult, raw_findings_to_views
from omnix.scan.turboscan.worker_pool import map_verify_tasks, map_verify_tasks_serial

_LOG = logging.getLogger("omnix.scan.turboscan.orchestrator")


class _SlotRegistry:
    def __init__(self, slots: Any) -> None:
        self._slots = slots

    def current_case(self):
        best = None
        best_m = -1
        try:
            snap = dict(self._slots)
        except Exception:
            return None
        for _k, v in snap.items():
            if not isinstance(v, dict):
                continue
            m = int(v.get("mono") or 0)
            if m > best_m and v.get("relp"):
                best_m = m
                best = (
                    str(v["relp"]),
                    str(v["fn"]),
                    str(v.get("repro") or ""),
                    int(v.get("lineno") or 0),
                )
        return best


def worker_slot_count(requested: int | None) -> int:
    n = requested if requested is not None else min(os.cpu_count() or 4, 8)
    n = max(1, min(int(n), 8))
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    if kb < 4 * 1024 * 1024:
                        n = min(n, 4)
                    break
    except OSError:
        pass
    return n


def dispatch_turboscan_python_phase(
    *,
    root: Path,
    paths: list[Path],
    base_run: dict[str, Any],
    examples_default: int,
    workers: int | None,
    filesystem_hygiene: bool,
    delegated_hygiene: bool,
    include_private: bool,
    findings: list[dict[str, Any]],
    import_errs: list[dict[str, Any]],
    timeouts: list[dict[str, Any]],
    skipped_main: list[dict[str, Any]],
    in_cnt: dict[str, int],
    entry_reach_map: dict[str, bool],
    cc: dict[str, int],
    gctx: dict[str, Any],
    src_root: str,
    gpath: str,
    croot: str,
    verify_ws: str,
    plan_only: bool,
    total_timeout_s: float = 300.0,
    scan_monotonic_start: float | None = None,
) -> tuple[int, int, BudgetPlan | None, list[str]]:
    """Run (or plan) parallel verify for Python targets.

    Returns ``(fcount_delta, ex_total_delta, budget_plan, relative_paths_touched)``.
    """
    from omnix.find_bugs.entry_points import detect_framework_decorated, graph_id_for
    from omnix.find_bugs.runner import (
        _apply_one_verify_outcome,
        _relpos,
        _skip_for_main_transparency,
    )
    from omnix.scan.turboscan.calibration import ensure_turboscan_calibration
    from omnix.verify.signature import extract_signatures

    root = root.resolve()
    ensure_turboscan_calibration(root)
    workers_w = worker_slot_count(workers)
    fcount = 0
    targets: list[tuple[str, str, int, Path]] = []
    for fpath in paths:
        relp = _relpos(fpath, root)
        try:
            sigs = extract_signatures(fpath, None)
        except (OSError, SyntaxError, ValueError) as e:
            import_errs.append(
                {
                    "kind": "import_error",
                    "file": relp,
                    "message": f"extract_signatures: {e!s}",
                }
            )
            continue
        frame_skip = {n: r for n, r in detect_framework_decorated(fpath)}
        for s in sigs:
            fn = str(s.get("name", ""))
            fcount += 1
            if not include_private and fn.startswith("_"):
                continue
            sk = _skip_for_main_transparency(fpath, fn)
            if sk:
                skipped_main.append({"file": relp, "function": fn, "reason": sk})
                continue
            fwr = frame_skip.get(fn)
            if fwr is not None:
                skipped_main.append({"file": relp, "function": fn, "reason": fwr})
                continue
            lineno = int(s.get("lineno", 0) or 0)
            targets.append((relp, fn, lineno, fpath.resolve()))

    if not targets:
        return fcount, 0, None, []

    budget = build_budget_plan(
        root,
        targets,
        worker_slots=workers_w,
        examples_default=examples_default,
    )
    budget_map = budget.by_function_key()
    rels_order = [t[0] for t in targets]

    payloads: list[dict[str, Any]] = []
    for relp, fn, lineno, fpath in targets:
        ex = budget_map.get((relp, fn), examples_default)
        slot = hash((relp, fn)) % workers_w
        hyp_d = str(worker_hypothesis_dir(root, slot))
        ra = {
            **base_run,
            "target_path": str(fpath),
            "function": fn,
            "examples": int(ex),
            "hypothesis_database_directory": hyp_d,
        }
        if delegated_hygiene:
            ra["fs_hygiene_delegated"] = True
        repro = (
            f"PYTHONPATH={shlex.quote(src_root)} {shlex.quote(sys.executable)} "
            f"-m omnix.verify.cli {shlex.quote(str(fpath))} "
            f"--function {shlex.quote(fn)} --examples {int(ex)} "
            f"--json --no-receipt "
            f"--graph-db {shlex.quote(gpath)} "
            f"--codebase-root {shlex.quote(croot)} "
            f"--verify-workspace {shlex.quote(str(Path(verify_ws).resolve()))}"
        )
        payloads.append(
            {
                "slot": slot,
                "relp": relp,
                "fn": fn,
                "lineno": lineno,
                "examples": int(ex),
                "run_args": ra,
                "repro": repro,
            }
        )

    if plan_only:
        return fcount, 0, budget, rels_order

    ex_total = 0
    mgr = Manager()
    slots = mgr.dict()
    registry = _SlotRegistry(slots)
    session = None

    def _enrich_hygiene(fd: dict[str, Any]) -> None:
        rel = str(fd.get("file") or "")
        fn0 = str(fd.get("function") or "")
        fk = graph_id_for(rel, fn0)
        fd["caller_count"] = int(in_cnt.get(fk, 0) or 0)
        fd["reachable_from_entries"] = bool(entry_reach_map.get(fk, False))
        fd["cluster_id"] = cc.get(fk)
        fd.setdefault("failures", [])
        findings.append(fd)

    try:
        if delegated_hygiene and filesystem_hygiene:
            cfg = load_sandbox_config_from_env()
            if cfg is not None:
                roots = validated_sandbox_roots(cfg)
                session = start_hygiene_watcher(
                    repo_root=root,
                    sandbox_roots=roots,
                    tmp_root=cfg.resolved_tmp_root(),
                    registry=registry,
                    on_finding=_enrich_hygiene,
                    reproduction_template=os.environ.get(
                        "OMNIX_FS_HYGIENE_REPRO_CMD",
                        "python -m omnix.verify.cli <target> --function <name> --json --no-receipt",
                    ),
                    force_polling=parse_bool_env(
                        "OMNIX_TURBOSCAN_FORCE_POLLING", False
                    ),
                )
            else:
                _LOG.warning(
                    "turboscan: hygiene delegated but sandbox config missing — skipping watcher"
                )

        serial = os.environ.get("OMNIX_TURBOSCAN_SERIAL", "").lower() in (
            "1",
            "true",
            "yes",
        )
        raw_results: list[dict[str, Any]] = []
        chunk_sz = max(workers_w * 4, 16)
        mono0 = (
            float(scan_monotonic_start)
            if scan_monotonic_start is not None
            else time.monotonic()
        )
        use_deadline = bool(total_timeout_s and total_timeout_s > 0)
        for i in range(0, len(payloads), chunk_sz):
            if use_deadline and (time.monotonic() - mono0) > float(total_timeout_s):
                print(
                    f"WARN: total scan timeout ({int(total_timeout_s)}s) reached "
                    f"after processing {len(raw_results)} / {len(payloads)} function "
                    "verifies; partial results returned",
                    file=sys.stderr,
                )
                break
            chunk = payloads[i : i + chunk_sz]
            if serial or workers_w <= 1:
                raw_results.extend(map_verify_tasks_serial(chunk, slots))
            else:
                raw_results.extend(
                    map_verify_tasks(workers_w, chunk, shared_slots=slots)
                )

        for r in raw_results:
            ex_total += _apply_one_verify_outcome(
                code=int(r["code"]),
                out=str(r["out"]),
                werr=r.get("werr"),
                relp=str(r["relp"]),
                fn=str(r["fn"]),
                lineno=int(r["lineno"]),
                examples=int(r["examples"]),
                filesystem_hygiene=filesystem_hygiene,
                findings=findings,
                import_errs=import_errs,
                timeouts=timeouts,
                in_cnt=in_cnt,
                entry_reach_map=entry_reach_map,
                cc=cc,
                gctx=gctx,
                worker_internal_err=r.get("worker_err"),
            )
    finally:
        if session is not None:
            session.stop()
        mgr.shutdown()

    return fcount, ex_total, budget, rels_order


def scan(
    codebase_path: str | Path,
    *,
    mode: str = "full",
    workers: int | None = None,
    examples_default: int = 100,
    plan_only: bool = False,
) -> TurboScanResult:
    """Public TURBOSCAN entry used by benchmarks/tests."""
    from omnix.find_bugs.runner import run_find_bugs

    incremental = mode == "incremental"
    t0 = time.perf_counter()
    exit_code, text_out, detail = run_find_bugs(
        str(codebase_path),
        examples=examples_default,
        json_mode=True,
        no_bundle=True,
        turboscan=True,
        incremental=incremental,
        plan_only=plan_only,
        turboscan_workers=workers,
    )
    wall = time.perf_counter() - t0
    findings_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    if isinstance(detail, dict):
        raw = detail.get("findings")
        if isinstance(raw, list):
            findings_rows = [x for x in raw if isinstance(x, dict)]
        s = detail.get("summary")
        if isinstance(s, dict):
            summary = s
    budget_used = int(summary.get("total_examples_run") or 0)
    budget_total = int(summary.get("turboscan_budget_total") or budget_used)
    paths = summary.get("turboscan_paths")
    path_list = [str(x) for x in paths] if isinstance(paths, list) else []
    return TurboScanResult(
        findings=raw_findings_to_views(findings_rows),
        scan_completed_successfully=exit_code != 2,
        wall_clock_seconds=float(summary.get("wall_time_seconds") or wall),
        files_scanned=path_list,
        budget_plan=None,
        budget_used=budget_used,
        scan_phase=str(summary.get("scan_phase") or "done"),
        wall_clock_ms=int(float(summary.get("wall_clock_ms") or wall * 1000)),
        plan_only=plan_only,
    )
