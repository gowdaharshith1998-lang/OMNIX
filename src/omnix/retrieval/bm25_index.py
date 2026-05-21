"""BM25 index over enriched COBOL graph node summaries."""

from __future__ import annotations

import math
import re
from collections import Counter

from omnix.enrich.common import enriched_text
from omnix.graph.store import GraphStore


class Bm25Index:
    def __init__(self, graph_store: GraphStore) -> None:
        self.graph_store = graph_store
        graph_store.sqlite_connection().executescript(
            """
            CREATE TABLE IF NOT EXISTS bm25_index (
                node_id TEXT PRIMARY KEY,
                text TEXT NOT NULL
            );
            """
        )
        graph_store.commit()

    def rebuild_from_graph(self, graph_store: GraphStore | None = None) -> None:
        store = graph_store or self.graph_store
        conn = store.sqlite_connection()
        conn.execute("DELETE FROM bm25_index")
        rows = [(node.id, enriched_text(node)) for node in store.iter_all_nodes() if enriched_text(node)]
        conn.executemany("INSERT OR REPLACE INTO bm25_index(node_id, text) VALUES (?, ?)", rows)
        store.commit()

    def query(self, text: str, top_k: int = 20) -> list[tuple[str, float]]:
        rows = self.graph_store.sqlite_connection().execute("SELECT node_id, text FROM bm25_index").fetchall()
        corpus = [(str(row[0]), str(row[1])) for row in rows]
        if not corpus:
            return []
        query_terms = _tokenize(text)
        if not query_terms:
            return []
        docs = [Counter(_tokenize(doc)) for _node_id, doc in corpus]
        avgdl = sum(sum(doc.values()) for doc in docs) / max(1, len(docs))
        scores: list[tuple[str, float]] = []
        for (node_id, _doc_text), doc in zip(corpus, docs, strict=False):
            score = 0.0
            dl = sum(doc.values()) or 1
            for term in query_terms:
                freq = doc.get(term, 0)
                if not freq:
                    continue
                df = sum(1 for candidate in docs if candidate.get(term, 0) > 0)
                idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
                score += idf * (freq * 2.2) / (freq + 1.2 * (1 - 0.75 + 0.75 * dl / avgdl))
            if score > 0:
                scores.append((node_id, score))
        return sorted(scores, key=lambda item: (-item[1], item[0]))[:top_k]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())
