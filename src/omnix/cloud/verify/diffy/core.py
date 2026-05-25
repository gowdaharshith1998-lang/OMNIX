"""Diffy core — noise-filtered diff and async proxy."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _is_jsonish(v: Any) -> bool:
    return isinstance(v, (dict, list, int, float, str, bool, type(None)))


def _walk(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            out.update(_walk(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_walk(v, f"{prefix}[{i}]"))
    else:
        out[prefix or "$"] = obj
    return out


def semantic_diff(a: Any, b: Any) -> set[str]:
    """Return the set of leaf-paths where ``a`` and ``b`` disagree."""
    flat_a = _walk(a)
    flat_b = _walk(b)
    keys = set(flat_a) | set(flat_b)
    diff: set[str] = set()
    for k in keys:
        if flat_a.get(k, _Sentinel) != flat_b.get(k, _Sentinel):
            diff.add(k)
    return diff


class _Sentinel:
    pass


@dataclass
class NoiseFilter:
    """Records primary-vs-secondary differences so they can be subtracted
    from candidate-vs-primary on the next request."""
    paths: set[str] = field(default_factory=set)
    samples: int = 0

    def observe(self, primary_response: Any, secondary_response: Any) -> None:
        self.samples += 1
        self.paths |= semantic_diff(primary_response, secondary_response)

    def filter(self, diff: set[str]) -> set[str]:
        return diff - self.paths


@dataclass
class DiffyResult:
    request_id: str
    candidate_diff: set[str]
    candidate_diff_after_noise: set[str]
    noise_paths: set[str]
    primary_status: int
    candidate_status: int


@dataclass
class DiffyReport:
    total: int = 0
    matched: int = 0
    mismatched: int = 0
    by_path: dict[str, int] = field(default_factory=dict)

    def absorb(self, result: DiffyResult) -> None:
        self.total += 1
        if not result.candidate_diff_after_noise:
            self.matched += 1
        else:
            self.mismatched += 1
            for p in result.candidate_diff_after_noise:
                self.by_path[p] = self.by_path.get(p, 0) + 1


class DiffyProxy:
    """Pluggable async multicast proxy.

    Real deployments wire ``send(client, url, payload)`` to httpx. Tests can
    pass an in-process fake.
    """

    def __init__(self, primary: str, secondary: str, candidate: str,
                 *, sender=None, noise: NoiseFilter | None = None) -> None:
        self.primary = primary
        self.secondary = secondary
        self.candidate = candidate
        self._sender = sender
        self.noise = noise or NoiseFilter()
        self.report = DiffyReport()

    async def forward(self, request_id: str, payload: Any) -> DiffyResult:
        sender = self._sender or _default_httpx_sender()
        p, s, c = await asyncio.gather(
            sender(self.primary, payload),
            sender(self.secondary, payload),
            sender(self.candidate, payload),
        )
        # Compute noise via primary↔secondary; refresh the filter.
        primary_body, primary_status = p
        secondary_body, _ = s
        candidate_body, candidate_status = c

        self.noise.observe(primary_body, secondary_body)
        raw = semantic_diff(primary_body, candidate_body)
        filtered = self.noise.filter(raw)

        result = DiffyResult(
            request_id=request_id,
            candidate_diff=raw,
            candidate_diff_after_noise=filtered,
            noise_paths=set(self.noise.paths),
            primary_status=primary_status,
            candidate_status=candidate_status,
        )
        self.report.absorb(result)
        return result


def _default_httpx_sender():
    """Return an httpx-based sender. Imported lazily so tests don't need httpx live."""
    import httpx

    async def sender(url: str, payload: Any) -> tuple[Any, int]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, content=json.dumps(payload).encode())
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            return body, resp.status_code

    return sender
