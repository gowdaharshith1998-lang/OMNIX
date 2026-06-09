from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


def safe_workspace_file_path(root: Path, raw_path: str) -> tuple[Path, str]:
    cleaned = (raw_path or "").replace("\\", "/")
    rel = Path(cleaned)
    if rel.is_absolute() or ".." in rel.parts or not cleaned.strip("/"):
        raise HTTPException(400, "invalid path")
    resolved_root = root.resolve()
    full = (resolved_root / rel).resolve()
    if full != resolved_root and resolved_root not in full.parents:
        raise HTTPException(400, "invalid path")
    return full, rel.as_posix()
