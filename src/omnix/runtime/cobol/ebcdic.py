"""EBCDIC detection and normalization."""

from __future__ import annotations


def detect_ebcdic(data: bytes) -> bool:
    if not data:
        return False
    hi = sum(1 for b in data if b >= 0x80)
    hi_ratio = hi / max(1, len(data))
    periodic_4b = sum(1 for b in data if b == 0x4B) / max(1, len(data))
    return hi_ratio > 0.05 and periodic_4b > 0.005


def normalize_ebcdic(data: bytes, *, no_detect: bool = False) -> str:
    if no_detect:
        return data.decode("utf-8", errors="replace")
    if not detect_ebcdic(data):
        return data.decode("utf-8", errors="replace")
    for enc in ("cp1047", "cp037"):
        try:
            return data.decode(enc)
        except LookupError:
            continue
    return data.decode("latin-1", errors="replace")
