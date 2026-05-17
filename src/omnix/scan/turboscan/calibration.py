"""Hot Hypothesis generator calibration (R2.1.3 / R2.1.7)."""

from __future__ import annotations

import cProfile
import json
import logging
import os
import pstats
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hypothesis.internal.conjecture.data import ConjectureData

_LOG = logging.getLogger("omnix.scan.turboscan.calibration")


def _strategy_file(repo_root: Path) -> Path:
    return (repo_root / "src" / "verify" / "strategies.py").resolve()


def _default_cache_path(repo_root: Path) -> Path:
    return (repo_root / ".omnix" / "turboscan" / "calibration.json").resolve()


@dataclass(frozen=True)
class GeneratorCalibrationEntry:
    name: str
    cumulative_ms: float
    call_count: int
    avg_per_call_ms: float


@dataclass(frozen=True)
class CalibrationReport:
    top_generators: tuple[GeneratorCalibrationEntry, ...]
    strategies_mtime_ns: int
    wall_seconds: float


def _bench_draws(name: str, strategy: Any, iterations: int, rng_seed: int = 0) -> None:
    del name  # used only as profiler label via caller module globals
    from random import Random

    rnd = Random(rng_seed)
    for i in range(iterations):
        rnd.seed(rng_seed + i)
        strategy.do_draw(ConjectureData(random=rnd))


def _run_benchmark_profile(
    benches: list[tuple[str, Any, int]],
) -> list[tuple[str, float, int]]:
    """Return (name, cumulative_seconds, call_count) per bench via cProfile."""
    results: list[tuple[str, float, int]] = []
    for name, strat, n_calls in benches:
        pr = cProfile.Profile()

        def _one_loop(
            _nm: str = name,
            _st: Any = strat,
            _nc: int = n_calls,
        ) -> None:
            _bench_draws(_nm, _st, _nc)

        pr.enable()
        _one_loop()
        pr.disable()
        stats = pstats.Stats(pr)
        stats.sort_stats("cumulative")
        total_ms = stats.total_tt * 1000.0
        results.append((name, stats.total_tt, n_calls))
        _LOG.debug(
            "calibration bench %s: %.2fms over %d draws", name, total_ms, n_calls
        )
    results.sort(key=lambda x: x[1], reverse=True)
    return [(name, tt, cc) for name, tt, cc in results]


def calibrate_hot_generators(
    repo_root: str | Path,
    *,
    cache_dir: Path | None = None,
    layer_budgets: dict[str, float] | None = None,
    iterations_per_strategy: int = 800,
) -> CalibrationReport:
    """Profile fixed omnix verify strategies; cache under ``.omnix/turboscan/``."""
    root = Path(repo_root).resolve()
    strat_path = _strategy_file(root)
    mtime_ns = (
        int(strat_path.stat().st_mtime_ns)
        if strat_path.is_file()
        else 0
    )

    cache_path = (
        Path(cache_dir).resolve() / "calibration.json"
        if cache_dir is not None
        else _default_cache_path(root)
    )

    if cache_path.is_file():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if int(raw.get("strategies_mtime_ns") or 0) == mtime_ns:
                entries = raw.get("top_generators") or []
                top: list[GeneratorCalibrationEntry] = []
                for e in entries[:5]:
                    top.append(
                        GeneratorCalibrationEntry(
                            name=str(e["name"]),
                            cumulative_ms=float(e["cumulative_ms"]),
                            call_count=int(e["call_count"]),
                            avg_per_call_ms=float(e["avg_per_call_ms"]),
                        )
                    )
                if len(top) == 5:
                    return CalibrationReport(
                        top_generators=tuple(top),
                        strategies_mtime_ns=mtime_ns,
                        wall_seconds=float(raw.get("wall_seconds") or 0.0),
                    )
        except (OSError, ValueError, KeyError, TypeError) as e:
            _LOG.debug("calibration cache read failed: %s", e)

    import hypothesis.strategies as st

    benches: list[tuple[str, Any, int]] = [
        ("omnix_inline.text", st.text(), iterations_per_strategy),
        ("omnix_inline.integers", st.integers(), iterations_per_strategy),
        ("omnix_inline.broad_one_of", st.one_of(st.integers(), st.text(), st.none(), st.booleans()), iterations_per_strategy),  # noqa: E501
        ("omnix_inline.booleans", st.booleans(), iterations_per_strategy),
        ("omnix_inline.none", st.none(), iterations_per_strategy),
    ]

    t_wall0 = time.perf_counter()
    ranked = _run_benchmark_profile(benches)
    wall = time.perf_counter() - t_wall0

    cap = (layer_budgets or {}).get("calibration")
    if cap is not None and wall > cap * 1.5:
        dom = ", ".join(x[0] for x in ranked[:3])
        _LOG.warning(
            "CALIBRATION_BUDGET_BREACH layer=calibration allocated=%.3fs observed=%.3fs generators=%s",
            cap,
            wall,
            dom,
        )

    top5 = ranked[:5]
    report_entries: list[GeneratorCalibrationEntry] = []
    for name, cum_s, calls in top5:
        ms = cum_s * 1000.0
        report_entries.append(
            GeneratorCalibrationEntry(
                name=name,
                cumulative_ms=ms,
                call_count=calls,
                avg_per_call_ms=ms / max(1, calls),
            )
        )

    report = CalibrationReport(
        top_generators=tuple(report_entries),
        strategies_mtime_ns=mtime_ns,
        wall_seconds=wall,
    )

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "strategies_mtime_ns": mtime_ns,
            "wall_seconds": wall,
            "top_generators": [asdict(e) for e in report_entries],
        }
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as e:
        _LOG.warning("calibration cache write failed: %s", e)

    return report


def ensure_turboscan_calibration(repo_root: str | Path) -> CalibrationReport:
    """Load or refresh calibration and enable verify-time substitutions."""
    report = calibrate_hot_generators(repo_root)
    os.environ["OMNIX_TURBOSCAN_INLINE"] = "1"
    return report
