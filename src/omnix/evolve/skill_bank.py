"""SQLite-backed bi-temporal skill bank."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from omnix.enrich.common import utc_now_iso
from omnix.graph.store import GraphStore


@dataclass(frozen=True)
class Skill:
    skill_id: str
    title: str
    description: str
    match_predicate: dict[str, Any]
    prompt_addendum: str
    version: int = 1
    embedding: list[float] | None = None
    t_created: str = ""
    t_valid: str = ""
    t_invalid: str | None = None
    t_expired: str | None = None
    provenance_hard_cases: list[str] | None = None


class SkillBank:
    def __init__(self, graph_store: GraphStore) -> None:
        self.graph_store = graph_store
        graph_store.sqlite_connection().executescript(
            """
            CREATE TABLE IF NOT EXISTS skill_bank (
                skill_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                match_predicate TEXT NOT NULL,
                prompt_addendum TEXT NOT NULL,
                embedding TEXT,
                t_created TEXT NOT NULL,
                t_valid TEXT NOT NULL,
                t_invalid TEXT,
                t_expired TEXT,
                provenance_hard_cases TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skill_active ON skill_bank(t_invalid, t_expired)
                WHERE t_invalid IS NULL AND t_expired IS NULL;
            """
        )
        graph_store.commit()

    def add(self, skill: Skill) -> str:
        now = utc_now_iso()
        skill_id = skill.skill_id or f"skill-{uuid.uuid4()}"
        self.graph_store.sqlite_connection().execute(
            """
            INSERT OR REPLACE INTO skill_bank (
                skill_id, version, title, description, match_predicate, prompt_addendum,
                embedding, t_created, t_valid, t_invalid, t_expired, provenance_hard_cases
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill_id,
                skill.version,
                skill.title,
                skill.description,
                json.dumps(skill.match_predicate, sort_keys=True),
                skill.prompt_addendum,
                json.dumps(skill.embedding) if skill.embedding is not None else None,
                skill.t_created or now,
                skill.t_valid or now,
                skill.t_invalid,
                skill.t_expired,
                json.dumps(skill.provenance_hard_cases or []),
            ),
        )
        self.graph_store.commit()
        return skill_id

    def get_active(self) -> list[Skill]:
        rows = self.graph_store.sqlite_connection().execute(
            "SELECT * FROM skill_bank WHERE t_invalid IS NULL AND t_expired IS NULL ORDER BY title"
        ).fetchall()
        return [_row_to_skill(row) for row in rows]

    def invalidate(self, skill_id: str, reason: str = "") -> None:
        _ = reason
        self.graph_store.sqlite_connection().execute(
            "UPDATE skill_bank SET t_invalid = ? WHERE skill_id = ?",
            (utc_now_iso(), skill_id),
        )
        self.graph_store.commit()

    def list_all(self, include_invalid: bool = False) -> list[Skill]:
        where = "" if include_invalid else "WHERE t_invalid IS NULL AND t_expired IS NULL"
        rows = self.graph_store.sqlite_connection().execute(
            f"SELECT * FROM skill_bank {where} ORDER BY title"
        ).fetchall()
        return [_row_to_skill(row) for row in rows]

    def check_for_regression(self, graph_store: GraphStore, last_n_rebuilds: int = 5) -> list[str]:
        _ = graph_store, last_n_rebuilds
        return []


def _row_to_skill(row: Any) -> Skill:
    return Skill(
        skill_id=str(row["skill_id"]),
        version=int(row["version"]),
        title=str(row["title"]),
        description=str(row["description"]),
        match_predicate=json.loads(row["match_predicate"]),
        prompt_addendum=str(row["prompt_addendum"]),
        embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        t_created=str(row["t_created"]),
        t_valid=str(row["t_valid"]),
        t_invalid=row["t_invalid"],
        t_expired=row["t_expired"],
        provenance_hard_cases=json.loads(row["provenance_hard_cases"] or "[]"),
    )
