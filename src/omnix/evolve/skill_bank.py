"""SQLite-backed bi-temporal skill bank."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
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


@dataclass(frozen=True)
class _RebuildMetric:
    passed: bool
    skill_ids: set[str]


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

    def check_for_regression(
        self,
        graph_store: GraphStore,
        last_n_rebuilds: int = 5,
        *,
        drop_pct_threshold: float = 15.0,
        min_applications: int = 3,
        runs_dir: Path | None = None,
    ) -> list[str]:
        active_ids = {skill.skill_id for skill in self.get_active()}
        if not active_ids:
            return []
        metrics = _recent_rebuild_metrics(
            runs_dir or _default_runs_dir(graph_store),
            last_n_rebuilds=last_n_rebuilds,
        )
        if not metrics:
            return []
        baseline_pass_rate = sum(1 for metric in metrics if metric.passed) / len(metrics)
        threshold = drop_pct_threshold / 100.0
        regressed: list[str] = []
        for skill_id in sorted(active_ids):
            applied = [metric for metric in metrics if skill_id in metric.skill_ids]
            if len(applied) < min_applications:
                continue
            skill_pass_rate = sum(1 for metric in applied if metric.passed) / len(applied)
            if baseline_pass_rate - skill_pass_rate >= threshold:
                regressed.append(skill_id)
        return regressed

    def auto_rollback_on_regression(
        self,
        graph_store: GraphStore,
        last_n_rebuilds: int = 5,
        *,
        drop_pct_threshold: float = 15.0,
        min_applications: int = 3,
        runs_dir: Path | None = None,
    ) -> list[str]:
        regressed = self.check_for_regression(
            graph_store,
            last_n_rebuilds=last_n_rebuilds,
            drop_pct_threshold=drop_pct_threshold,
            min_applications=min_applications,
            runs_dir=runs_dir,
        )
        for skill_id in regressed:
            self.invalidate(skill_id, "auto rollback: regression detected")
        return regressed


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


def _default_runs_dir(graph_store: GraphStore) -> Path:
    db_path = Path(graph_store.db_path)
    if db_path.parent.name == ".omnix":
        return db_path.parent / "runs"
    return db_path.parent / ".omnix" / "runs"


def _recent_rebuild_metrics(runs_dir: Path, *, last_n_rebuilds: int) -> list[_RebuildMetric]:
    if last_n_rebuilds <= 0 or not runs_dir.is_dir():
        return []
    metrics: list[_RebuildMetric] = []
    run_dirs = sorted((path for path in runs_dir.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
    for run_dir in run_dirs:
        receipts_dir = run_dir / "receipts"
        if not receipts_dir.is_dir():
            continue
        for receipt_path in sorted(receipts_dir.glob("*.json")):
            if receipt_path.name.endswith(".provenance.json"):
                continue
            metric = _read_rebuild_metric(receipt_path)
            if metric is None:
                continue
            metrics.append(metric)
            if len(metrics) >= last_n_rebuilds:
                return metrics
    return metrics


def _read_rebuild_metric(receipt_path: Path) -> _RebuildMetric | None:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    gates = receipt.get("gate_results")
    if not isinstance(gates, list):
        return None
    passed = bool(gates) and all(isinstance(gate, dict) and gate.get("status") == "passed" for gate in gates)
    return _RebuildMetric(passed=passed, skill_ids=_sidecar_skill_ids(receipt_path.with_suffix(".provenance.json")))


def _sidecar_skill_ids(sidecar_path: Path) -> set[str]:
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    raw_skills = sidecar.get("skills_applied")
    if not isinstance(raw_skills, list):
        return set()
    skill_ids: set[str] = set()
    for skill in raw_skills:
        if isinstance(skill, dict):
            skill_id = skill.get("skill_id") or skill.get("id")
        else:
            skill_id = skill
        if skill_id:
            skill_ids.add(str(skill_id))
    return skill_ids
