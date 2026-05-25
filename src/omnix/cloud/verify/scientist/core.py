"""GitHub Scientist — in-process dual-run experiment harness."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class Branch:
    name: str
    value: Any
    duration_ms: float
    exception: str | None = None


@dataclass
class Mismatch:
    experiment: str
    control: Branch
    candidate: Branch
    context: dict[str, Any] = field(default_factory=dict)


class ResultPublisher(Protocol):
    def __call__(self, mismatch: Mismatch) -> None: ...


def list_publisher(sink: list[Mismatch]) -> ResultPublisher:
    def _publish(m: Mismatch) -> None:
        sink.append(m)
    return _publish


def jsonl_publisher(path: str | Path) -> ResultPublisher:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _publish(m: Mismatch) -> None:
        with p.open("a") as f:
            payload = {
                "experiment": m.experiment,
                "context": m.context,
                "control": asdict(m.control),
                "candidate": asdict(m.candidate),
            }
            f.write(json.dumps(payload, default=repr))
            f.write("\n")

    return _publish


def _default_comparator(a: Any, b: Any) -> bool:
    return a == b


def _measure(fn: Callable, *args, **kwargs) -> tuple[Any, float, str | None]:
    start = time.perf_counter()
    try:
        value = fn(*args, **kwargs)
        return value, (time.perf_counter() - start) * 1000, None
    except Exception:  # noqa: BLE001
        return None, (time.perf_counter() - start) * 1000, traceback.format_exc(limit=4)


async def _measure_async(fn: Callable, *args, **kwargs) -> tuple[Any, float, str | None]:
    start = time.perf_counter()
    try:
        value = fn(*args, **kwargs)
        if inspect.isawaitable(value):
            value = await value
        return value, (time.perf_counter() - start) * 1000, None
    except Exception:  # noqa: BLE001
        return None, (time.perf_counter() - start) * 1000, traceback.format_exc(limit=4)


class Experiment:
    """Single experiment.

    Reads from `control` (the legacy behaviour) and shadows with `candidate`.
    Always returns the control result. Mismatches are published via the configured
    `ResultPublisher`; the experiment never raises on mismatch — it's observational.
    """

    def __init__(
        self,
        name: str,
        *,
        publisher: ResultPublisher | None = None,
        comparator: Callable[[Any, Any], bool] = _default_comparator,
        enabled: Callable[[], bool] = lambda: True,
        raise_on_mismatch: bool = False,
    ) -> None:
        self.name = name
        self._control: Callable | None = None
        self._candidate: Callable | None = None
        self._publisher: ResultPublisher | None = publisher
        self._comparator = comparator
        self._enabled = enabled
        self._raise = raise_on_mismatch

    # Decorators
    def use(self, fn: Callable) -> Callable:
        self._control = fn
        return fn

    def try_(self, fn: Callable) -> Callable:
        self._candidate = fn
        return fn

    # Runtime
    def run(self, *args: Any, **kwargs: Any) -> Any:
        if self._control is None:
            raise RuntimeError(f"experiment {self.name!r} has no control")
        control_value, ctrl_ms, ctrl_exc = _measure(self._control, *args, **kwargs)
        control = Branch("control", control_value, ctrl_ms, ctrl_exc)
        if ctrl_exc:
            raise RuntimeError(f"control raised: {ctrl_exc}")

        if not (self._enabled() and self._candidate is not None):
            return control_value

        cand_value, cand_ms, cand_exc = _measure(self._candidate, *args, **kwargs)
        candidate = Branch("candidate", cand_value, cand_ms, cand_exc)

        agree = cand_exc is None and self._comparator(control_value, cand_value)
        if not agree:
            mismatch = Mismatch(
                experiment=self.name,
                control=control,
                candidate=candidate,
                context={"args": [repr(a) for a in args], "kwargs": {k: repr(v) for k, v in kwargs.items()}},
            )
            if self._publisher:
                self._publisher(mismatch)
            if self._raise:
                raise AssertionError(f"experiment {self.name!r}: {mismatch}")
        return control_value

    async def run_async(self, *args: Any, **kwargs: Any) -> Any:
        if self._control is None:
            raise RuntimeError(f"experiment {self.name!r} has no control")
        if not (self._enabled() and self._candidate is not None):
            v, _, exc = await _measure_async(self._control, *args, **kwargs)
            if exc:
                raise RuntimeError(f"control raised: {exc}")
            return v

        control_task = asyncio.create_task(_measure_async(self._control, *args, **kwargs))
        candidate_task = asyncio.create_task(_measure_async(self._candidate, *args, **kwargs))
        (control_value, ctrl_ms, ctrl_exc), (cand_value, cand_ms, cand_exc) = await asyncio.gather(
            control_task, candidate_task
        )
        if ctrl_exc:
            raise RuntimeError(f"control raised: {ctrl_exc}")
        control = Branch("control", control_value, ctrl_ms, ctrl_exc)
        candidate = Branch("candidate", cand_value, cand_ms, cand_exc)
        if cand_exc is not None or not self._comparator(control_value, cand_value):
            if self._publisher:
                self._publisher(
                    Mismatch(
                        experiment=self.name,
                        control=control,
                        candidate=candidate,
                        context={"args": [repr(a) for a in args],
                                 "kwargs": {k: repr(v) for k, v in kwargs.items()}},
                    )
                )
            if self._raise:
                raise AssertionError(f"experiment {self.name!r} mismatch")
        return control_value
