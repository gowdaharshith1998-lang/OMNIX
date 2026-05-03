"""Provider key auto-detection via prefix match and safe model-list probes."""

from __future__ import annotations

import json
import urllib.parse
import urllib.error
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fabric.providers.common import request_json
from providers.registry import (
    AMBIGUOUS_PROBE_PRIORITY,
    PREFIX_PRIORITY,
    PREFIXLESS_PROBE_PRIORITY,
    PROVIDERS,
    ProviderSpec,
)


@dataclass(frozen=True)
class DetectionResult:
    provider: str
    confidence: float
    method: str

    def to_dict(self) -> dict[str, str | float]:
        return asdict(self)


def _audit(provider: str, outcome: str) -> None:
    root = Path.home() / ".omnix" / "audit"
    try:
        root.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider": provider,
            "outcome": outcome,
        }
        with (root / "provider_probes.log").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        return


def _prefix_matches(raw_key: str) -> list[str]:
    candidates: list[tuple[int, str]] = []
    for name in PREFIX_PRIORITY:
        spec = PROVIDERS[name]
        matched = [prefix for prefix in spec.prefix_patterns if raw_key.startswith(prefix)]
        if matched:
            candidates.append((max(len(prefix) for prefix in matched), name))
    if not candidates:
        return []
    longest = max(length for length, _name in candidates)
    return [name for length, name in candidates if length == longest]


def _probe_url(spec: ProviderSpec, raw_key: str) -> str:
    if spec.base_url is None:
        return ""
    endpoint = spec.probe_endpoint.format(key=urllib.parse.quote(raw_key, safe=""))
    return spec.base_url.rstrip("/") + endpoint


def _probe(provider: str, raw_key: str, timeout_s: float = 5.0) -> bool:
    spec = PROVIDERS[provider]
    url = _probe_url(spec, raw_key)
    if not url:
        _audit(provider, "skipped")
        return False
    headers = dict(spec.probe_extra_headers)
    if spec.probe_auth is not None:
        h, tmpl = spec.probe_auth
        headers[h] = tmpl.format(key=raw_key)
    try:
        status, _data = request_json(
            url,
            method="GET",
            headers=headers,
            body=None,
            timeout_s=timeout_s,
        )
    except urllib.error.URLError:
        _audit(provider, "network_error")
        return False
    ok = status == 200
    _audit(provider, "ok" if ok else f"http_{status}")
    return ok


async def identify_provider(
    raw_key: str,
    custom_base_url: str | None = None,
) -> DetectionResult:
    if custom_base_url:
        return DetectionResult("custom", 1.0, "user_specified")

    matches = _prefix_matches(raw_key)
    if len(matches) == 1:
        return DetectionResult(matches[0], 1.0, "prefix")

    if len(matches) > 1:
        ordered = [p for p in AMBIGUOUS_PROBE_PRIORITY if p in matches]
        ordered.extend(p for p in matches if p not in ordered)
        for provider in ordered:
            if _probe(provider, raw_key):
                return DetectionResult(provider, 0.9, "probe")
        return DetectionResult("unknown", 0.0, "none")

    for provider in PREFIXLESS_PROBE_PRIORITY:
        if _probe(provider, raw_key):
            return DetectionResult(provider, 0.8, "probe")
    return DetectionResult("unknown", 0.0, "none")
