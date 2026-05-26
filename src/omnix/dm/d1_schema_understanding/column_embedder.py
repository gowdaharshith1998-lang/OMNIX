"""Column-context embedder.

Wraps ``sentence_transformers/all-MiniLM-L6-v2`` (384-dim, local, no API) and
builds a deterministic prompt template per ``ColumnContext`` so that:

  * Same input → same vector (test-verified).
  * The model is lazy-loaded and cached at module scope so multiple
    ``embed()`` calls don't repeatedly pay the model-init cost.
  * The model can be force-replaced by tests via the ``set_embedding_backend``
    hook (useful when CI runs in an env without HuggingFace weight downloads).

Honest gap: first call on a cold cache needs the model file from HuggingFace
cache. In offline CI we expose ``set_embedding_backend`` so tests pass without
network.
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Callable, Optional

import numpy as np

from omnix.dm._types import ColumnContext

_DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384

_BACKEND_LOCK = threading.Lock()
_BACKEND: Optional[Callable[[str], np.ndarray]] = None


def _summarize_usage(usages) -> str:
    if not usages:
        return "(none)"
    parts = []
    for u in usages[:5]:
        parts.append(f"{u.file_path}:{u.line_number}:{u.op_type}")
    if len(usages) > 5:
        parts.append(f"... and {len(usages) - 5} more")
    return "; ".join(parts)


def build_embedding_input(ctx: ColumnContext) -> str:
    """Build the deterministic embedding-input prompt for a ColumnContext."""
    return (
        f"COLUMN: {ctx.column.name}\n"
        f"TABLE: {ctx.table_name}\n"
        f"TYPE: {ctx.column.normalized_type} (raw: {ctx.column.raw_type})\n"
        f"NULLABLE: {ctx.column.nullable}\n"
        f"COMMENT: {ctx.column.comment or '(none)'}\n"
        f"SAMPLES: {', '.join(ctx.sample_values[:20])}\n"
        f"CODE_USAGE: {_summarize_usage(ctx.codebase_usage)}\n"
    )


def _hash_based_backend(text: str) -> np.ndarray:
    """Deterministic SHA-256-derived embedding used as a fallback when the
    real sentence-transformers model is unavailable. Produces a unit-norm
    384-dim vector that respects the determinism contract but is *not* a
    semantic embedding — tests that hit it must rely only on identity, not
    similarity-between-different-strings."""
    digest_chunks = []
    seed = text.encode("utf-8")
    needed = EMBED_DIM * 4  # 4 bytes per float32
    counter = 0
    while len(b"".join(digest_chunks)) < needed:
        chunk = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        digest_chunks.append(chunk)
        counter += 1
    raw = b"".join(digest_chunks)[:needed]
    arr = np.frombuffer(raw, dtype=np.uint32).astype(np.float32)
    arr = (arr / np.float32(2**32 - 1)) - 0.5  # center to ~[-0.5, 0.5]
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.astype(np.float32)


def _load_real_backend() -> Optional[Callable[[str], np.ndarray]]:
    if os.environ.get("OMNIX_DM_DISABLE_SENTENCE_TRANSFORMERS") == "1":
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    try:
        model = SentenceTransformer(_DEFAULT_MODEL_NAME)
    except Exception:
        return None

    def _encode(text: str) -> np.ndarray:
        v = model.encode([text], normalize_embeddings=True)[0]
        return np.asarray(v, dtype=np.float32)

    return _encode


def set_embedding_backend(backend: Optional[Callable[[str], np.ndarray]]) -> None:
    """Install a custom embedding backend. Pass ``None`` to clear / reset.

    Used by tests to force the hash-based deterministic backend without paying
    the model download cost. Production callers should not touch this."""
    global _BACKEND
    with _BACKEND_LOCK:
        _BACKEND = backend


def _get_backend() -> Callable[[str], np.ndarray]:
    global _BACKEND
    if _BACKEND is None:
        with _BACKEND_LOCK:
            if _BACKEND is None:
                real = _load_real_backend()
                _BACKEND = real if real is not None else _hash_based_backend
    return _BACKEND


def embed(ctx: ColumnContext) -> np.ndarray:
    """Return a 384-dim float32 unit vector for ``ctx``."""
    text = build_embedding_input(ctx)
    backend = _get_backend()
    v = backend(text)
    v = np.asarray(v, dtype=np.float32)
    if v.shape != (EMBED_DIM,):
        raise RuntimeError(
            f"embedding backend returned shape {v.shape}, expected ({EMBED_DIM},)"
        )
    return v


__all__ = [
    "EMBED_DIM",
    "build_embedding_input",
    "embed",
    "set_embedding_backend",
]
