"""Hard-case buffer for failed-then-passed Reflexion transitions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from omnix.enrich.common import utc_now_iso
from omnix.graph.store import GraphStore


@dataclass(frozen=True)
class HardCase:
    entry_id: str
    program_id: str
    failure_analysis: str
    successful_prompt_addendum: str
    byte_diff_signature: str
    failure_count: int = 1
    t_created: str = ""
    t_expired: str | None = None


class HardCaseBuffer:
    def __init__(self, graph_store: GraphStore) -> None:
        self.graph_store = graph_store
        graph_store.sqlite_connection().executescript(
            """
            CREATE TABLE IF NOT EXISTS hard_case_buffer (
                entry_id TEXT PRIMARY KEY,
                program_id TEXT NOT NULL,
                failure_analysis TEXT NOT NULL,
                successful_prompt_addendum TEXT NOT NULL,
                byte_diff_signature TEXT NOT NULL,
                failure_count INTEGER NOT NULL DEFAULT 1,
                t_created TEXT NOT NULL,
                t_expired TEXT
            );
            """
        )
        graph_store.commit()

    def append(self, entry: HardCase) -> str:
        entry_id = entry.entry_id or f"hard-{uuid.uuid4()}"
        self.graph_store.sqlite_connection().execute(
            """
            INSERT OR REPLACE INTO hard_case_buffer (
                entry_id, program_id, failure_analysis, successful_prompt_addendum,
                byte_diff_signature, failure_count, t_created, t_expired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                entry.program_id,
                entry.failure_analysis,
                entry.successful_prompt_addendum,
                entry.byte_diff_signature,
                entry.failure_count,
                entry.t_created or utc_now_iso(),
                entry.t_expired,
            ),
        )
        self.graph_store.commit()
        return entry_id

    def get_pending_for_designer(self) -> list[HardCase]:
        rows = self.graph_store.sqlite_connection().execute(
            "SELECT * FROM hard_case_buffer WHERE t_expired IS NULL ORDER BY t_created"
        ).fetchall()
        return [_row_to_case(row) for row in rows]

    def expire(self, entry_ids: list[str]) -> None:
        if not entry_ids:
            return
        self.graph_store.sqlite_connection().executemany(
            "UPDATE hard_case_buffer SET t_expired = ? WHERE entry_id = ?",
            [(utc_now_iso(), entry_id) for entry_id in entry_ids],
        )
        self.graph_store.commit()

    def prune_by_age(self, max_age_days: int = 30) -> None:
        self.graph_store.sqlite_connection().execute(
            "DELETE FROM hard_case_buffer WHERE julianday('now') - julianday(t_created) > ?",
            (max_age_days,),
        )
        self.graph_store.commit()

    def prune_by_capacity(self, max_entries: int = 200) -> None:
        self.graph_store.sqlite_connection().execute(
            """
            DELETE FROM hard_case_buffer
            WHERE entry_id NOT IN (
                SELECT entry_id FROM hard_case_buffer ORDER BY t_created DESC LIMIT ?
            )
            """,
            (max_entries,),
        )
        self.graph_store.commit()


def _row_to_case(row) -> HardCase:
    return HardCase(
        entry_id=str(row["entry_id"]),
        program_id=str(row["program_id"]),
        failure_analysis=str(row["failure_analysis"]),
        successful_prompt_addendum=str(row["successful_prompt_addendum"]),
        byte_diff_signature=str(row["byte_diff_signature"]),
        failure_count=int(row["failure_count"]),
        t_created=str(row["t_created"]),
        t_expired=row["t_expired"],
    )
