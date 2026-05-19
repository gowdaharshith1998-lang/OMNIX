"""Copybook resolution and safety checks."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


class InvalidCopybookPath(ValueError):
    """Raised when a copybook search path is unsafe."""


_SHELL_META_RE = re.compile(r"[;|`]|\$\(")


@dataclass(frozen=True)
class ResolvedCopybook:
    name: str
    resolved: bool
    path: str | None
    content: str | None


def validate_copybook_path(path_value: str) -> str:
    if _SHELL_META_RE.search(path_value):
        raise InvalidCopybookPath(f"invalid copybook path: {path_value!r}")
    return path_value


def build_search_paths(
    explicit: list[str] | None,
    *,
    env_cobcpy: str | None = None,
) -> list[Path]:
    out: list[Path] = []
    for raw in explicit or []:
        out.append(Path(validate_copybook_path(raw)).expanduser())
    env_raw = env_cobcpy if env_cobcpy is not None else os.environ.get("COBCPY", "")
    if env_raw:
        for item in env_raw.split(os.pathsep):
            item = item.strip()
            if not item:
                continue
            out.append(Path(validate_copybook_path(item)).expanduser())
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in out:
        k = str(p)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def resolve_copybook(copy_name: str, search_paths: list[Path]) -> Path | None:
    cands = [copy_name]
    if not copy_name.lower().endswith(".cpy"):
        cands.append(f"{copy_name}.cpy")
    for base in search_paths:
        for c in cands:
            p = (base / c).resolve()
            if p.is_file():
                return p
    return None


def resolve_copybooks_in_text(text: str, search_paths: list[Path]) -> tuple[str, list[ResolvedCopybook]]:
    refs: list[ResolvedCopybook] = []
    out_lines: list[str] = []
    copy_re = re.compile(r"^\s*COPY\s+([A-Z0-9_-]+)(?:\.CPY)?\s*\.?\s*$", re.IGNORECASE)

    for line in text.splitlines():
        m = copy_re.match(line)
        if not m:
            out_lines.append(line)
            continue
        name = m.group(1)
        hit = resolve_copybook(name, search_paths)
        if hit is None:
            refs.append(ResolvedCopybook(name=name, resolved=False, path=None, content=None))
            out_lines.append(line)
            continue
        content = hit.read_text(encoding="utf-8", errors="replace")
        refs.append(ResolvedCopybook(name=name, resolved=True, path=str(hit), content=content))
        out_lines.append(f"      * BEGIN COPY {name}")
        out_lines.extend(content.splitlines())
        out_lines.append(f"      * END COPY {name}")
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else ""), refs
