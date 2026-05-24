"""Vector index with sqlite-vec-compatible table names and BGE/hash embeddings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from typing import Any, Literal

from omnix.enrich.common import enriched_text
from omnix.graph.store import GraphStore

NodeType = Literal["paragraphs", "programs", "copybooks", "data_items"]
TABLES: dict[str, str] = {
    "CobolParagraph": "vec_paragraphs",
    "CobolProgram": "vec_programs",
    "CobolModule": "vec_programs",
    "CobolCopybook": "vec_copybooks",
    "CobolDataItem": "vec_data_items",
}
_MODEL_CACHE: Any | None = None
_MODEL_LOAD_ATTEMPTED = False
_REAL_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class VectorIndex:
    def __init__(self, graph_store: GraphStore) -> None:
        self.graph_store = graph_store
        conn = graph_store.sqlite_connection()
        for table in sorted(set(TABLES.values())):
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    node_id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    text TEXT NOT NULL
                )
                """
            )
        graph_store.commit()

    def upsert(self, node_id: str, node_type: str, text: str) -> None:
        table = _table_for(node_type)
        self.graph_store.sqlite_connection().execute(
            f"INSERT OR REPLACE INTO {table}(node_id, embedding, text) VALUES (?, ?, ?)",
            (node_id, json.dumps(embed_text(text)), text),
        )
        self.graph_store.commit()

    def rebuild_from_graph(self, graph_store: GraphStore | None = None) -> None:
        store = graph_store or self.graph_store
        conn = store.sqlite_connection()
        for table in sorted(set(TABLES.values())):
            conn.execute(f"DELETE FROM {table}")
        for node in store.iter_all_nodes():
            text = enriched_text(node)
            if text and node.type in TABLES:
                self.upsert(node.id, node.type, text)
        store.commit()

    def query(self, text: str, node_type: str = "programs", top_k: int = 20) -> list[tuple[str, float]]:
        table = _table_for(node_type)
        target = embed_text(text)
        rows = self.graph_store.sqlite_connection().execute(
            f"SELECT node_id, embedding FROM {table}"
        ).fetchall()
        scored = []
        for row in rows:
            emb = json.loads(str(row["embedding"]))
            distance = 1.0 - cosine_similarity(target, emb)
            scored.append((str(row["node_id"]), distance))
        return sorted(scored, key=lambda item: (item[1], item[0]))[:top_k]


def _table_for(node_type: str) -> str:
    if node_type in TABLES:
        return TABLES[node_type]
    normalized = node_type.lower()
    if normalized in {"paragraph", "paragraphs"}:
        return "vec_paragraphs"
    if normalized in {"program", "programs", "module", "modules"}:
        return "vec_programs"
    if normalized in {"copybook", "copybooks"}:
        return "vec_copybooks"
    if normalized in {"data_item", "data_items", "dataitem"}:
        return "vec_data_items"
    raise ValueError(f"unknown vector node type: {node_type}")


def _embed_mode() -> Literal["auto", "real", "hash"]:
    value = os.environ.get("OMNIX_GRAPHRAG_EMBED_MODE", "auto").strip().lower()
    if value == "real":
        return "real"
    if value == "hash":
        return "hash"
    return "auto"


def _get_real_model() -> Any | None:
    global _MODEL_CACHE, _MODEL_LOAD_ATTEMPTED
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if _MODEL_LOAD_ATTEMPTED:
        return None
    _MODEL_LOAD_ATTEMPTED = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        _MODEL_CACHE = SentenceTransformer(_REAL_MODEL_NAME)
    except Exception as exc:  # pragma: no cover - exercised with import monkeypatches
        print(
            f"OMNIX GraphRAG embedding model unavailable; using hash fallback: {exc}",
            file=sys.stderr,
        )
        return None
    return _MODEL_CACHE


def _embed_text_hash(text: str, dims: int = 384) -> list[float]:
    # Deterministic local fallback keeps tests offline and avoids model downloads.
    vec = [0.0] * dims
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8", errors="replace")).digest()
        idx = int.from_bytes(digest[:4], "big") % dims
        sign = -1.0 if digest[4] % 2 else 1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_text(text: str, dims: int = 384) -> list[float]:
    mode = _embed_mode()
    if mode == "hash":
        return _embed_text_hash(text, dims=dims)

    model = _get_real_model()
    if model is None:
        if mode == "real":
            raise RuntimeError("OMNIX_GRAPHRAG_EMBED_MODE=real but model unavailable")
        return _embed_text_hash(text, dims=dims)

    encoded = model.encode(text, normalize_embeddings=True)
    values = encoded.tolist() if hasattr(encoded, "tolist") else encoded
    vec = [float(value) for value in values[:dims]]
    if len(vec) < dims:
        vec.extend([0.0] * (dims - len(vec)))
    return vec


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    n = min(len(left), len(right))
    dot = sum(left[i] * right[i] for i in range(n))
    ln = math.sqrt(sum(x * x for x in left[:n])) or 1.0
    rn = math.sqrt(sum(x * x for x in right[:n])) or 1.0
    return dot / (ln * rn)
