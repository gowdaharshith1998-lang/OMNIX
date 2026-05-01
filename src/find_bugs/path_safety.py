"""Safe filename handling for find_bugs artifact paths (debt-19)."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

_LOG = logging.getLogger("omnix.find_bugs.path_safety")

_MAX_NAME_LEN = 64
_SAFE_CHARS = re.compile(r"[^a-zA-Z0-9_.-]+")


def sanitize_filename(name: str, *, max_len: int = _MAX_NAME_LEN) -> str | None:
    """Return a single path segment safe for use as a filename, or None if unusable.

    Allows only ``[a-zA-Z0-9_.-]``, bounded length. Rejects empty, ``.``, ``..``,
    embedded NUL, and leading ``-`` (shell/flag hazards). Non-ASCII and other
    characters are replaced with ``_`` or a short ``h<hex>`` hash when the result
    would otherwise be empty.
    """
    if not name or "\x00" in name:
        return None
    s = _SAFE_CHARS.sub("_", name).strip("_")
    if ".." in s:
        digest = hashlib.sha256(name.encode("utf-8", errors="surrogateescape")).hexdigest()[:16]
        s = f"h{digest}"
    if not s or s in (".", ".."):
        digest = hashlib.sha256(name.encode("utf-8", errors="surrogateescape")).hexdigest()[:16]
        s = f"h{digest}"
    if s.startswith("-"):
        s = f"f{s.lstrip('-') or 'x'}"
    if len(s) > max_len:
        s = s[: max_len - 9] + "_" + hashlib.sha256(name.encode("utf-8", errors="surrogateescape")).hexdigest()[:8]
    if not s or s in (".", ".."):
        return None
    return s


def resolved_path_under(base: Path, candidate: Path) -> Path | None:
    """Return *candidate* if its resolved path stays under *base* (both resolved)."""
    try:
        b = base.resolve()
        c = candidate.resolve()
    except (OSError, ValueError):
        return None
    try:
        c.relative_to(b)
    except ValueError:
        return None
    return c


def safe_output_path(output_dir: Path, filename: str) -> Path | None:
    """Join *filename* (sanitized) under *output_dir*; refuse escapes."""
    out = output_dir.resolve()
    seg = sanitize_filename(filename)
    if seg is None:
        _LOG.warning("find_bugs: rejected unusable artifact filename after sanitization")
        return None
    cand = (out / seg).resolve()
    if resolved_path_under(out, cand) is None:
        _LOG.warning(
            "find_bugs: refused write outside output dir (%s -> %s)",
            output_dir,
            cand,
        )
        return None
    return cand
