"""GitHub-Scientist Python port — standalone surface.

This is a re-export of the cloud package's verify.scientist core. We keep
the file structure parallel so the two implementations cannot drift.
"""

from __future__ import annotations

import json
import os
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
            f.write(json.dumps({
                "experiment": m.experiment,
                "context": m.context,
                "control": asdict(m.control),
                "candidate": asdict(m.candidate),
            }, default=repr))
            f.write("\n")
    return _publish


def http_publisher(base_url: str, *, token: str | None = None) -> ResultPublisher:
    token = token or os.environ.get("OMNIX_TENANT_TOKEN")

    def _publish(m: Mismatch) -> None:
        try:
            import httpx
            httpx.post(
                f"{base_url}/v1/scientist/mismatches",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                json={
                    "experiment": m.experiment,
                    "context": m.context,
                    "control": asdict(m.control),
                    "candidate": asdict(m.candidate),
                },
                timeout=10,
            )
        except Exception:
            pass  # never break the user's request path on a publish failure
    return _publish


def _measure(fn: Callable, *args, **kwargs) -> tuple[Any, float, str | None]:
    start = time.perf_counter()
    try:
        return fn(*args, **kwargs), (time.perf_counter() - start) * 1000, None
    except Exception:
        return None, (time.perf_counter() - start) * 1000, traceback.format_exc(limit=4)


class Experiment:
    def __init__(self, name: str, *, publisher: ResultPublisher | None = None,
                 comparator: Callable[[Any, Any], bool] | None = None,
                 enabled: Callable[[], bool] = lambda: True) -> None:
        self.name = name
        self._control: Callable | None = None
        self._candidate: Callable | None = None
        self._publisher = publisher
        self._comparator = comparator or (lambda a, b: a == b)
        self._enabled = enabled

    def use(self, fn: Callable) -> Callable:
        self._control = fn
        return fn

    def try_(self, fn: Callable) -> Callable:
        self._candidate = fn
        return fn

    def run(self, *args: Any, **kwargs: Any) -> Any:
        if self._control is None:
            raise RuntimeError(f"experiment {self.name!r} has no control")
        control_value, ctrl_ms, ctrl_exc = _measure(self._control, *args, **kwargs)
        if ctrl_exc:
            raise RuntimeError(f"control raised: {ctrl_exc}")
        if not (self._enabled() and self._candidate is not None):
            return control_value
        cand_value, cand_ms, cand_exc = _measure(self._candidate, *args, **kwargs)
        agree = cand_exc is None and self._comparator(control_value, cand_value)
        if not agree and self._publisher:
            self._publisher(Mismatch(
                experiment=self.name,
                control=Branch("control", control_value, ctrl_ms, ctrl_exc),
                candidate=Branch("candidate", cand_value, cand_ms, cand_exc),
                context={"args": [repr(a) for a in args],
                         "kwargs": {k: repr(v) for k, v in kwargs.items()}},
            ))
        return control_value
