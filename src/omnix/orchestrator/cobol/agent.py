"""Sequential COBOL modernization agent loop."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from omnix.graph.store import GraphStore
from omnix.orchestrator.cobol.audit_export import copy_receipt_to_run, export_audit_zip
from omnix.orchestrator.cobol.decision_queue import DecisionOption, DecisionQueue, DecisionRequest
from omnix.orchestrator.cobol.discovery import DiscoveredProgram, discover
from omnix.orchestrator.cobol.run_state import ProgramStateRow, RunState
from omnix.parser.ingest_dispatch import ingest_unified_codebase
from omnix.rebuild.cobol_runner import (
    CobolRebuildError,
    GateFailure,
    iter_cobol_programs,
    rebuild_cobol_program,
)
from omnix.runtime.cobol.capture import run_capture
from omnix.runtime.cobol.gnucobol_adapter import compile_cobol
from omnix.spec.cobol_hypothesis import generate_spec

RebuildHook = Callable[[DiscoveredProgram, Path], Path]
StepHook = Callable[..., object]


@dataclass(frozen=True)
class AgentConfig:
    codebase_root: Path
    target_language: str = "python"
    budget_usd: float = 10.0
    max_gate6_retries: int = 2
    auto_skip_no_fixtures: bool = False
    halt_on_failure: bool = False
    decision_timeout_s: float = 60.0
    no_auto_audit: bool = False
    fixtures_root: Path | None = None
    rebuild_fn: RebuildHook | None = None
    capture_fn: StepHook | None = None
    spec_gen_fn: StepHook | None = None


@dataclass(frozen=True)
class AgentSummary:
    run_id: str
    verified: int
    gate6_failed: int
    skipped: int
    errored: int
    total_spend_usd: Decimal
    elapsed_seconds: float
    receipts_dir: Path
    audit_zip: Path | None


class ModernizeAgent:
    def __init__(self, config: AgentConfig, *, run_state: RunState, decision_queue: DecisionQueue) -> None:
        self.config = config
        self.run_state = run_state
        self.decision_queue = decision_queue

    def run(self) -> AgentSummary:
        started = time.monotonic()
        discovery = discover(self.config.codebase_root, fixtures_root=self.config.fixtures_root)
        self.run_state.emit_event("run_started", {"program_count": len(discovery.programs)})
        for program in discovery.programs:
            self.run_state.add_program(program)
        self._ensure_graph()
        for program in discovery.programs:
            row = self.run_state.get_program(program.program_id)
            if row.state in {"verified", "gate6_failed", "skipped", "error"}:
                continue
            self._run_program(program)
        audit_zip = None
        if not self.config.no_auto_audit and any(row.state == "verified" for row in self.run_state.all_programs()):
            audit_zip = export_audit_zip(
                run_state=self.run_state,
                out_path=self.run_state.run_dir / f"audit-{self.run_state.run_id}.zip",
            )
        summary = self._summary(started, audit_zip)
        status = "completed" if summary.errored == 0 and summary.gate6_failed == 0 else "failed"
        self.run_state.finish(status)
        self.run_state.emit_event("run_completed", {"verified": summary.verified, "skipped": summary.skipped})
        return summary

    def resume(self) -> AgentSummary:
        return self.run()

    def _run_program(self, program: DiscoveredProgram) -> None:
        if not program.fixture_paths:
            decision = "s" if self.config.auto_skip_no_fixtures else self._ask_missing_fixtures(program)
            if decision == "s":
                self.run_state.transition(program.program_id, "skipped", last_error="missing fixtures")
                return
            if decision == "g":
                program = self._with_generated_fixture(program)
            else:
                self.run_state.transition(program.program_id, "skipped", last_error=f"unsupported decision {decision}")
                return
        try:
            self._capture(program)
            self.run_state.transition(program.program_id, "captured")
            self._spec_gen(program)
            self.run_state.transition(program.program_id, "spec_generated")
            self.run_state.transition(program.program_id, "rebuilding")
            receipt = self._rebuild(program)
            copied = copy_receipt_to_run(receipt, self.run_state.run_dir / "receipts")
            self.run_state.transition(program.program_id, "verified", receipt_path=str(copied))
        except GateFailure as exc:
            if exc.gate_number == 6:
                self.run_state.transition(
                    program.program_id,
                    "gate6_failed",
                    gate6_attempts=self.config.max_gate6_retries,
                    last_error=str(exc.details),
                )
                if self.config.halt_on_failure:
                    raise
                return
            self._error_or_halt(program, exc)
        except CobolRebuildError as exc:
            self._error_or_halt(program, exc)
        except (OSError, ValueError, RuntimeError) as exc:
            self._error_or_halt(program, exc)

    def _capture(self, program: DiscoveredProgram) -> None:
        if self.config.capture_fn is not None:
            self.config.capture_fn(program)
            return
        fixtures = _prepared_fixtures(program, self.run_state.run_dir / "fixtures")
        executable = compile_cobol(program.source_path, out_dir=self.run_state.run_dir / "bin")
        run_capture(
            project_root=self.config.codebase_root,
            program=executable,
            fixtures_dir=fixtures,
            output_root=self.config.codebase_root / ".omnix" / "captures" / "cobol" / program.program_id,
        )

    def _spec_gen(self, program: DiscoveredProgram) -> None:
        if self.config.spec_gen_fn is not None:
            self.config.spec_gen_fn(program)
            return
        generate_spec(
            program.program_id,
            self.config.codebase_root / ".omnix" / "captures" / "cobol",
            Path.cwd() / "tests" / "cobol" / "generated",
        )

    def _rebuild(self, program: DiscoveredProgram) -> Path:
        receipts_dir = self.run_state.run_dir / "raw_receipts"
        if self.config.rebuild_fn is not None:
            return self.config.rebuild_fn(program, receipts_dir)
        db = self.config.codebase_root / ".omnix" / "omnix.db"
        store = GraphStore(str(db))
        try:
            programs = iter_cobol_programs(store, self.config.codebase_root, node_filter=f"*{program.program_id}*")
            if not programs:
                raise CobolRebuildError(f"COBOL program not found in graph: {program.program_id}")
            return rebuild_cobol_program(
                store=store,
                program_node_id=programs[0].node_id,
                target_language=self.config.target_language,
                receipts_dir=receipts_dir,
                keystore=None,
                llm_dispatch=None,
                project_path=self.config.codebase_root,
            )
        finally:
            store.close()

    def _ask_missing_fixtures(self, program: DiscoveredProgram) -> str:
        return self.decision_queue.ask(
            DecisionRequest(
                decision_id=f"{self.run_state.run_id}:{program.program_id}:missing_fixtures",
                kind="missing_fixtures",
                context={"program_id": program.program_id, "source_path": str(program.source_path)},
                options=(
                    DecisionOption("s", "Skip", "Skip and flag this program", recommended=True),
                    DecisionOption("g", "Generate", "Generate an empty synthetic fixture", cost_estimate_usd=0.0),
                ),
                default_key="s",
            ),
            timeout_s=self.config.decision_timeout_s,
        )

    def _with_generated_fixture(self, program: DiscoveredProgram) -> DiscoveredProgram:
        fixture = self.run_state.run_dir / "synthetic_inputs" / f"{program.program_id}.in"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(b"")
        return DiscoveredProgram(
            program.program_id,
            program.source_path,
            program.copybook_paths,
            [fixture],
            program.node_id,
        )

    def _ensure_graph(self) -> None:
        db = self.config.codebase_root / ".omnix" / "omnix.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        store = GraphStore(str(db))
        try:
            if store.node_count() == 0:
                ingest_unified_codebase(str(self.config.codebase_root), store)
        finally:
            store.close()

    def _error_or_halt(self, program: DiscoveredProgram, exc: Exception) -> None:
        self.run_state.transition(program.program_id, "error", last_error=str(exc))
        if self.config.halt_on_failure:
            raise exc

    def _summary(self, started: float, audit_zip: Path | None) -> AgentSummary:
        rows = self.run_state.all_programs()
        counts = _counts(rows)
        return AgentSummary(
            run_id=self.run_state.run_id,
            verified=counts["verified"],
            gate6_failed=counts["gate6_failed"],
            skipped=counts["skipped"],
            errored=counts["error"],
            total_spend_usd=self.run_state.total_spend(),
            elapsed_seconds=time.monotonic() - started,
            receipts_dir=self.run_state.run_dir / "receipts",
            audit_zip=audit_zip,
        )


def _prepared_fixtures(program: DiscoveredProgram, root: Path) -> Path:
    fixtures_root = root / program.program_id
    if fixtures_root.exists():
        shutil.rmtree(fixtures_root)
    fixtures_root.mkdir(parents=True)
    for idx, fixture in enumerate(program.fixture_paths):
        fixture_dir = fixtures_root / f"fixture-{idx + 1}"
        fixture_dir.mkdir()
        if fixture.is_dir():
            source = fixture / "input.bin"
            if source.is_file():
                shutil.copy2(source, fixture_dir / "input.bin")
            else:
                (fixture_dir / "input.bin").write_bytes(b"")
        else:
            shutil.copy2(fixture, fixture_dir / "input.bin")
    if not any(fixtures_root.iterdir()):
        empty = fixtures_root / "fixture-1"
        empty.mkdir()
        (empty / "input.bin").write_bytes(b"")
    return fixtures_root


def _counts(rows: list[ProgramStateRow]) -> dict[str, int]:
    return {
        "verified": sum(1 for row in rows if row.state == "verified"),
        "gate6_failed": sum(1 for row in rows if row.state == "gate6_failed"),
        "skipped": sum(1 for row in rows if row.state == "skipped"),
        "error": sum(1 for row in rows if row.state == "error"),
    }


def print_summary(summary: AgentSummary) -> str:
    audit = str(summary.audit_zip) if summary.audit_zip is not None else "<none>"
    return (
        f"Run {summary.run_id}\n"
        f"verified={summary.verified} gate6_failed={summary.gate6_failed} "
        f"skipped={summary.skipped} errored={summary.errored}\n"
        f"receipts={summary.receipts_dir}\n"
        f"audit={audit}\n"
    )


def configure_copybook_path(copybook_paths: list[Path]) -> None:
    dirs = sorted({str(path.parent) for path in copybook_paths})
    if not dirs:
        return
    existing = os.environ.get("COBCPY")
    os.environ["COBCPY"] = os.pathsep.join([*dirs, existing] if existing else dirs)
