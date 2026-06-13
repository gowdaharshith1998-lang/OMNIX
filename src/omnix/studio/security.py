from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException


def safe_workspace_file_path(root: Path, raw_path: str) -> tuple[Path, str]:
    cleaned = (raw_path or "").replace("\\", "/")
    rel = Path(cleaned)
    if rel.is_absolute() or ".." in rel.parts or not cleaned.strip("/"):
        raise HTTPException(400, "invalid path")
    # realpath + startswith (rather than Path.parents membership) keeps the
    # containment check in the shape CodeQL models as a path-injection
    # sanitizer; semantics are unchanged.
    root_str = os.path.realpath(str(root))
    full_str = os.path.realpath(os.path.join(root_str, cleaned))
    if full_str != root_str and not full_str.startswith(root_str + os.sep):
        raise HTTPException(400, "invalid path")
    return Path(full_str), rel.as_posix()
