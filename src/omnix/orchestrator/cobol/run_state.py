"""SQLite-backed COBOL orchestrator run state."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from omnix.orchestrator.cobol.discovery import DiscoveredProgram
from omnix.orchestrator.cobol.errors import StateCorrupted
from omnix.orchestrator.cobol.progress import utc_now_iso

TERMINAL_STATES = {"verified", "gate6_failed", "skipped", "error"}
VALID_STATES = {
    "discovered",
    "captured",
    "spec_generated",
    "rebuilding",
    *TERMINAL_STATES,
}


@dataclass(frozen=True)
class ProgramStateRow:
    run_id: str
    program_id: str
    source_path: str
    state: str
    gate6_attempts: int
    last_error: str | None
    receipt_path: str | None
    spend_usd: Decimal
    updated_at: str


class RunState:
    def __init__(self, run_id: str, run_dir: Path, conn: sqlite3.Connection) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    @classmethod
    def create(cls, codebase_root: Path, target_lang: str, budget_usd: float) -> RunState:
        root = codebase_root.resolve()
        run_id = f"{utc_now_iso().replace(':', '').replace('.', '')}-{uuid.uuid4().hex[:8]}"
        run_dir = root / ".omnix" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        conn = sqlite3.connect(run_dir / "state.db")
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO runs (
                run_id, codebase_root, target_lang, budget_usd, status,
                started_at, finished_at, total_spend_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, str(root), target_lang, float(budget_usd), "running", utc_now_iso(), None, 0.0),
        )
        conn.commit()
        return cls(run_id, run_dir, conn)

    @classmethod
    def resume(cls, run_id: str, *, runs_root: Path | None = None) -> RunState:
        root = runs_root or (Path.cwd() / ".omnix" / "runs")
        run_dir = root / run_id
        db = run_dir / "state.db"
        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            _ensure_schema(conn)
            row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        except sqlite3.DatabaseError as exc:
            raise StateCorrupted(f"cannot resume corrupted run state {db}: {exc}") from exc
        if row is None:
            conn.close()
            raise StateCorrupted(f"run state missing runs row for {run_id}")
        return cls(run_id, run_dir, conn)

    @property
    def codebase_root(self) -> Path:
        row = self._conn.execute("SELECT codebase_root FROM runs WHERE run_id = ?", (self.run_id,)).fetchone()
        return Path(str(row["codebase_root"]))

    def add_program(self, program: DiscoveredProgram) -> None:
        now = utc_now_iso()
        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO program_state (
                    run_id, program_id, source_path, state, gate6_attempts,
                    last_error, receipt_path, spend_usd, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    program.program_id,
                    str(program.source_path),
                    "discovered",
                    0,
                    None,
                    None,
                    0.0,
                    now,
                ),
            )

    def transition(self, program_id: str, new_state: str, **fields: object) -> None:
        if new_state not in VALID_STATES:
            raise ValueError(f"invalid program state: {new_state}")
        existing = self.get_program(program_id)
        updates: dict[str, object] = {"state": new_state, "updated_at": utc_now_iso(), **fields}
        allowed = {"state", "updated_at", "gate6_attempts", "last_error", "receipt_path", "spend_usd"}
        assignments = ", ".join(f"{key} = ?" for key in updates if key in allowed)
        values = [updates[key] for key in updates if key in allowed]
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE program_state SET {assignments} WHERE run_id = ? AND program_id = ?",
                (*values, self.run_id, program_id),
            )
            if cur.rowcount != 1:
                raise ValueError(f"invalid program state transition target: {program_id}")
            self.emit_event(
                "program_state_changed",
                {"program_id": program_id, "from_state": existing.state, "to_state": new_state},
            )

    def get_program(self, program_id: str) -> ProgramStateRow:
        row = self._conn.execute(
            "SELECT * FROM program_state WHERE run_id = ? AND program_id = ?",
            (self.run_id, program_id),
        ).fetchone()
        if row is None:
            raise ValueError(f"invalid program state target: {program_id}")
        return _program_row(row)

    def get_pending(self) -> list[ProgramStateRow]:
        rows = self._conn.execute(
            "SELECT * FROM program_state WHERE run_id = ? AND state NOT IN ('verified','gate6_failed','skipped','error') ORDER BY program_id",
            (self.run_id,),
        ).fetchall()
        return [_program_row(row) for row in rows]

    def get_terminal(self) -> list[ProgramStateRow]:
        rows = self._conn.execute(
            "SELECT * FROM program_state WHERE run_id = ? AND state IN ('verified','gate6_failed','skipped','error') ORDER BY program_id",
            (self.run_id,),
        ).fetchall()
        return [_program_row(row) for row in rows]

    def all_programs(self) -> list[ProgramStateRow]:
        rows = self._conn.execute(
            "SELECT * FROM program_state WHERE run_id = ? ORDER BY program_id", (self.run_id,)
        ).fetchall()
        return [_program_row(row) for row in rows]

    def total_spend(self) -> Decimal:
        row = self._conn.execute(
            "SELECT total_spend_usd AS total FROM runs WHERE run_id = ?",
            (self.run_id,),
        ).fetchone()
        return Decimal(str(row["total"] or 0))

    def add_spend(self, amount: Decimal) -> None:
        total = self.total_spend() + amount
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET total_spend_usd = ? WHERE run_id = ?",
                (float(total), self.run_id),
            )

    def finish(self, status: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (status, utc_now_iso(), self.run_id),
            )

    def put_decision_request(self, decision_id: str, kind: str, payload: dict[str, Any]) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO decisions (
                    run_id, decision_id, kind, payload_json, asked_at, answered_at, answer
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (self.run_id, decision_id, kind, json.dumps(payload, sort_keys=True), utc_now_iso(), None, None),
            )
        self.emit_event("decision_requested", {"decision_id": decision_id, "kind": kind})

    def answer_decision(self, decision_id: str, answer: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE decisions SET answered_at = ?, answer = ? WHERE run_id = ? AND decision_id = ?",
                (utc_now_iso(), answer, self.run_id, decision_id),
            )
        self.emit_event("decision_answered", {"decision_id": decision_id, "answer": answer})

    def get_decision(self, decision_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM decisions WHERE run_id = ? AND decision_id = ?",
            (self.run_id, decision_id),
        ).fetchone()
        if row is None:
            return {}
        return dict(row)

    def pending_decisions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE run_id = ? AND answer IS NULL ORDER BY asked_at",
            (self.run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def emit_event(self, kind: str, payload: dict[str, Any]) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO events (run_id, ts, level, kind, payload_json) VALUES (?, ?, ?, ?, ?)",
                (self.run_id, utc_now_iso(), "info", kind, json.dumps(payload, sort_keys=True)),
            )

    def events(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT run_id, ts, level, kind, payload_json FROM events WHERE run_id = ? ORDER BY ts",
            (self.run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> RunState:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def list_runs(*, runs_root: Path | None = None, status: str | None = None) -> list[dict[str, Any]]:
    root = runs_root or (Path.cwd() / ".omnix" / "runs")
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for db in sorted(root.glob("*/state.db"), reverse=True):
        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM runs").fetchone()
            conn.close()
        except sqlite3.DatabaseError:
            continue
        if row is None:
            continue
        item = dict(row)
        if status is None or item.get("status") == status:
            out.append(item)
    return out


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id text primary key,
            codebase_root text not null,
            target_lang text not null,
            budget_usd real not null,
            status text not null,
            started_at text not null,
            finished_at text,
            total_spend_usd real not null
        );
        CREATE TABLE IF NOT EXISTS program_state (
            run_id text not null,
            program_id text not null,
            source_path text not null,
            state text not null,
            gate6_attempts integer not null,
            last_error text,
            receipt_path text,
            spend_usd real not null,
            updated_at text not null,
            primary key (run_id, program_id)
        );
        CREATE TABLE IF NOT EXISTS decisions (
            run_id text not null,
            decision_id text not null,
            kind text not null,
            payload_json text not null,
            asked_at text not null,
            answered_at text,
            answer text,
            primary key (run_id, decision_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            run_id text not null,
            ts text not null,
            level text not null,
            kind text not null,
            payload_json text not null
        );
        """
    )
    conn.commit()


def _program_row(row: sqlite3.Row) -> ProgramStateRow:
    return ProgramStateRow(
        run_id=str(row["run_id"]),
        program_id=str(row["program_id"]),
        source_path=str(row["source_path"]),
        state=str(row["state"]),
        gate6_attempts=int(row["gate6_attempts"]),
        last_error=row["last_error"],
        receipt_path=row["receipt_path"],
        spend_usd=Decimal(str(row["spend_usd"] or 0)),
        updated_at=str(row["updated_at"]),
    )
