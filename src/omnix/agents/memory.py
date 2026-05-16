"""OMNIX Agent Memory — persistent learning across sessions."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime


class AgentMemory:
    """Persistent memory for AI agents — learns from past diagnoses."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.path.expanduser("~/.omnix/agent_memory.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS diagnoses (
                id TEXT PRIMARY KEY,
                codebase TEXT,
                directory TEXT,
                issue_type TEXT,
                root_cause TEXT,
                fix_applied TEXT,
                was_correct INTEGER DEFAULT -1,
                confidence REAL,
                provider TEXT,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codebase TEXT,
                pattern_type TEXT,
                description TEXT,
                frequency INTEGER DEFAULT 1,
                last_seen TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_diagnoses_codebase ON diagnoses(codebase);
            CREATE INDEX IF NOT EXISTS idx_patterns_codebase ON patterns(codebase);
            """
        )
        conn.close()

    def store_diagnosis(
        self,
        codebase: str,
        directory: str,
        issue_type: str,
        root_cause: str,
        fix: str,
        confidence: float,
        provider: str,
    ) -> str:
        """Store a diagnosis result."""
        conn = sqlite3.connect(self.db_path)
        diagnosis_id = f"{codebase}::{directory}::{issue_type}::{datetime.now().isoformat()}"
        conn.execute(
            "INSERT OR REPLACE INTO diagnoses (id, codebase, directory, issue_type, root_cause, fix_applied, confidence, provider, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                diagnosis_id,
                codebase,
                directory,
                issue_type,
                root_cause,
                fix,
                confidence,
                provider,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return diagnosis_id

    def find_similar(
        self, codebase: str, issue_type: str, limit: int = 5
    ) -> list[dict[str, object]]:
        """Find similar past diagnoses."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT root_cause, fix_applied, confidence, was_correct FROM diagnoses "
            "WHERE codebase = ? AND issue_type = ? ORDER BY timestamp DESC LIMIT ?",
            (codebase, issue_type, limit),
        )
        results = [
            {
                "root_cause": r[0],
                "fix": r[1],
                "confidence": r[2],
                "was_correct": r[3],
            }
            for r in cur.fetchall()
        ]
        conn.close()
        return results

    def mark_correct(self, diagnosis_id: str, correct: bool) -> None:
        """User feedback — was the diagnosis correct?"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE diagnoses SET was_correct = ? WHERE id = ?",
            (1 if correct else 0, diagnosis_id),
        )
        conn.commit()
        conn.close()

    def get_stats(self, codebase: str) -> dict[str, float | int]:
        """Get accuracy stats for a codebase."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN was_correct=1 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN was_correct=0 THEN 1 ELSE 0 END) "
            "FROM diagnoses WHERE codebase = ? AND was_correct != -1",
            (codebase,),
        )
        row = cur.fetchone()
        conn.close()
        total, correct, incorrect = row[0] or 0, row[1] or 0, row[2] or 0
        accuracy = (correct / total * 100) if total else 0.0
        return {
            "total": int(total),
            "correct": int(correct),
            "incorrect": int(incorrect),
            "accuracy": round(accuracy, 1),
        }
