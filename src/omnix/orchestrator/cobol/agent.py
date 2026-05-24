"""Sequential COBOL modernization agent loop."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from omnix.graph.store import GraphStore
from omnix.orchestrator.cobol.audit_export import copy_receipt_to_run, export_audit_zip
from omnix.orchestrator.cobol.decision_queue import DecisionOption, DecisionQueue, DecisionRequest
from omnix.orchestrator.cobol.discovery import DiscoveredProgram, discover
from omnix.orchestrator.cobol.reflexion import ReflexionContext, refine_prompt
from omnix.orchestrator.cobol.run_state import ProgramStateRow, RunState
from omnix.parser.ingest_dispatch import ingest_unified_codebase
from omnix.rebuild.cobol_runner import (
    CobolRebuildError,
    GateFailure,
    _default_llm_dispatch,
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
    graphrag_token_budget: int = 30000
    graphrag_hop_depth: int = 4
    graphrag_max_turns: int = 8
    graphrag_confidence_threshold: float = 0.75
    graphrag_skill_top_k: int = 3
    graphrag_model: str = "claude-sonnet-4.6"
    no_graphrag: bool = False


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
    accuracy_boost_metrics: dict[str, int] = field(default_factory=dict)


class ModernizeAgent:
    def __init__(self, config: AgentConfig, *, run_state: RunState, decision_queue: DecisionQueue) -> None:
        self.config = config
        self.run_state = run_state
        self.decision_queue = decision_queue
        self._graphrag_contexts: dict[str, dict] = {}
        self._accuracy_boost_metrics = {
            "rerank_invocations": 0,
            "mcts_invocations": 0,
            "ese_escalations": 0,
        }

    def run(self) -> AgentSummary:
        started = time.monotonic()
        discovery = discover(self.config.codebase_root, fixtures_root=self.config.fixtures_root)
        self.run_state.emit_event("run_started", {"program_count": len(discovery.programs)})
        configure_copybook_path([path for program in discovery.programs for path in program.copybook_paths])
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
            receipt, gate6_attempts = self._rebuild_with_gate6_retries(program)
            copied = copy_receipt_to_run(receipt, self.run_state.run_dir / "receipts")
            self._write_graphrag_sidecar(program, copied)
            self._auto_rollback_regressed_skills(program)
            self.run_state.transition(
                program.program_id,
                "verified",
                receipt_path=str(copied),
                gate6_attempts=gate6_attempts,
            )
        except GateFailure as exc:
            if exc.gate_number == 6:
                attempts = int(self.run_state.get_program(program.program_id).gate6_attempts)
                self._mark_gate6_failed(program, exc, attempts)
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

    def _rebuild_with_gate6_retries(self, program: DiscoveredProgram) -> tuple[Path, int]:
        attempts = 0
        gate6_failures: list[dict] | None = None
        while True:
            try:
                return self._rebuild(program, gate6_failures=gate6_failures), attempts
            except GateFailure as exc:
                if exc.gate_number != 6:
                    raise
                if attempts >= self.config.max_gate6_retries:
                    self._mark_gate6_failed(program, exc, attempts)
                    raise
                attempts += 1
                gate6_failures = list(exc.details.get("failures") or [])
                if attempts == 1:
                    gate6_failures = self._apply_accuracy_boost_retry_hooks(program, gate6_failures)
                self.run_state.transition(
                    program.program_id,
                    "rebuilding",
                    gate6_attempts=attempts,
                    last_error=str(exc.details),
                )

    def _rebuild(self, program: DiscoveredProgram, *, gate6_failures: list[dict] | None = None) -> Path:
        receipts_dir = self.run_state.run_dir / "raw_receipts"
        if self.config.rebuild_fn is not None:
            return self.config.rebuild_fn(program, receipts_dir)
        db = self.config.codebase_root / ".omnix" / "omnix.db"
        store = GraphStore(str(db))
        try:
            programs = iter_cobol_programs(store, self.config.codebase_root, node_filter=f"*{program.program_id}*")
            if not programs:
                raise CobolRebuildError(f"COBOL program not found in graph: {program.program_id}")
            target_node_id = resolve_graphrag_node_id(store, programs[0].node_id, program.program_id, program.source_path)
            llm_dispatch = _reflexion_dispatch(gate6_failures)
            if not self.config.no_graphrag and _has_target_enrichment(store, target_node_id):
                llm_dispatch = self._graphrag_dispatch(store, target_node_id, program.program_id, gate6_failures)
            return rebuild_cobol_program(
                store=store,
                program_node_id=programs[0].node_id,
                target_language=self.config.target_language,
                receipts_dir=receipts_dir,
                keystore=None,
                llm_dispatch=llm_dispatch,
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
        ensure_cobol_graph(self.config.codebase_root, db).close()

    def _error_or_halt(self, program: DiscoveredProgram, exc: Exception) -> None:
        self.run_state.transition(program.program_id, "error", last_error=str(exc))
        if self.config.halt_on_failure:
            raise exc

    def _mark_gate6_failed(self, program: DiscoveredProgram, exc: GateFailure, attempts: int) -> None:
        self.run_state.transition(
            program.program_id,
            "gate6_failed",
            gate6_attempts=attempts,
            last_error=str(exc.details),
        )

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
            accuracy_boost_metrics=dict(self._accuracy_boost_metrics),
        )

    def _apply_accuracy_boost_retry_hooks(
        self,
        program: DiscoveredProgram,
        gate6_failures: list[dict],
    ) -> list[dict]:
        thought = self._select_mcts_thought(program, gate6_failures)
        failures = [dict(failure) for failure in gate6_failures]
        if thought:
            for failure in failures:
                failure["mcts_thought"] = thought
        self._run_ese_cascade(program, failures)
        return failures

    def _select_mcts_thought(self, program: DiscoveredProgram, gate6_failures: list[dict]) -> str | None:
        from omnix.traversal import thought_mcts

        if not thought_mcts.mcts_enabled():
            return None
        seed_thoughts = [
            "focus on data-item padding",
            "focus on file output trailers",
            "focus on PERFORM ordering",
        ]

        def expand_fn(node: thought_mcts.ThoughtNode) -> list[str]:
            return [
                f"{node.thought} with fixture byte diffs",
                f"{node.thought} with graph neighbor evidence",
                f"{node.thought} with captured stdout comparison",
            ]

        def evaluate_fn(node: thought_mcts.ThoughtNode) -> float:
            return _score_thought_against_failures(node.thought, gate6_failures)

        best = thought_mcts.search(seed_thoughts, expand_fn, evaluate_fn)
        if best.thought == "root":
            return None
        self._accuracy_boost_metrics["mcts_invocations"] += 1
        self.run_state.emit_event(
            "mcts_thought_selected",
            {"program_id": program.program_id, "thought": best.thought, "visits": best.visits},
        )
        return best.thought

    def _run_ese_cascade(self, program: DiscoveredProgram, gate6_failures: list[dict]) -> None:
        from omnix.evolve import ensemble_entropy

        if ensemble_entropy.ese_mode() not in {"on", "auto"}:
            return
        outputs = [str(failure.get("candidate_stdout", "")) for failure in gate6_failures]
        outputs = [output for output in outputs if output]
        if not outputs:
            return
        idx = 0

        def generate_fn(_model_name: str) -> str:
            nonlocal idx
            output = outputs[idx % len(outputs)]
            idx += 1
            return output

        chosen, telemetry = ensemble_entropy.cascading_generate(generate_fn)
        escalations = max(0, len(telemetry.get("stages", [])) - 1)
        self._accuracy_boost_metrics["ese_escalations"] += escalations
        self.run_state.emit_event(
            "ese_cascade_evaluated",
            {
                "program_id": program.program_id,
                "chosen_output_sha256": hashlib.sha256(chosen.encode("utf-8")).hexdigest(),
                "telemetry": telemetry,
            },
        )

    def _graphrag_dispatch(
        self,
        store: GraphStore,
        target_node_id: str,
        program_id: str,
        gate6_failures: list[dict] | None,
    ) -> Callable[[str], str]:
        from omnix.evolve.controller import select_skills_for
        from omnix.evolve.skill_bank import SkillBank
        from omnix.retrieval.hybrid import retrieve

        def dispatch(prompt: str) -> str:
            try:
                bundle = retrieve(
                    store,
                    target_node_id,
                    budget_tokens=self.config.graphrag_token_budget,
                    hop_depth=self.config.graphrag_hop_depth,
                )
                skills = select_skills_for(
                    target_node_id,
                    store,
                    SkillBank(store),
                    top_k=self.config.graphrag_skill_top_k,
                )
                skill_text = "\n".join(skill.prompt_addendum for skill in skills)
                graphrag_context = (
                    "\n\n# GraphRAG context\n"
                    f"Target graph node: {target_node_id}\n"
                    f"Retrieval modes: {json.dumps(bundle.retrieval_modes, sort_keys=True)}\n"
                    f"Included graph context:\n{bundle.content}\n"
                )
                if gate6_failures:
                    from omnix.evolve.dual_evolve import parse_failure_analysis

                    graphrag_context += (
                        "\n# Failure-directed retrieval refinement\n"
                        + parse_failure_analysis(_gate6_failure_analysis_text(gate6_failures))
                        + "\n"
                    )
                if skill_text:
                    graphrag_context += "\n# Skills applied (from past rebuilds):\n" + skill_text + "\n"
                final_prompt = prompt + graphrag_context
                if gate6_failures:
                    final_prompt = refine_prompt(
                        ReflexionContext(
                            original_prompt=final_prompt,
                            failed_replica="",
                            gate6_failures=gate6_failures,
                        )
                    )
                    final_prompt = _append_accuracy_boost_notes(final_prompt, gate6_failures)
                self._graphrag_contexts[program_id] = {
                    "target_node_id": target_node_id,
                    "node_ids": bundle.node_ids,
                    "retrieval_modes": bundle.retrieval_modes,
                    "skills_applied": [
                        {"skill_id": skill.skill_id, "version": skill.version, "t_valid": skill.t_valid}
                        for skill in skills
                    ],
                    "token_cost": {
                        "retrieval": bundle.estimated_tokens,
                        "agent_loop": 0,
                        "generation": 0,
                        "designer": 0,
                    },
                    "enrichment_data_hash": hashlib.sha256(bundle.content.encode("utf-8")).hexdigest(),
                }
                if bundle.retrieval_modes.get("rerank"):
                    self._accuracy_boost_metrics["rerank_invocations"] += 1
                    self.run_state.emit_event(
                        "rerank_invoked",
                        {"program_id": program_id, "candidate_count": bundle.retrieval_modes["rerank"]},
                    )
                return _default_llm_dispatch(final_prompt)
            except Exception as exc:
                self.run_state.emit_event(
                    "graphrag_fallback",
                    {"program_id": program_id, "error": f"{type(exc).__name__}: {exc}"},
                )
                fallback_prompt = (
                    _append_accuracy_boost_notes(
                        refine_prompt(
                            ReflexionContext(
                                original_prompt=prompt,
                                failed_replica="",
                                gate6_failures=gate6_failures,
                            )
                        ),
                        gate6_failures,
                    )
                    if gate6_failures
                    else prompt
                )
                return _default_llm_dispatch(fallback_prompt)

        return dispatch

    def _write_graphrag_sidecar(self, program: DiscoveredProgram, receipt_path: Path) -> None:
        context = self._graphrag_contexts.get(program.program_id)
        if not context:
            return
        from omnix.provenance.sidecar import build_minimal_sidecar, write_sidecar
        from omnix.provenance.signer import SidecarSigner

        sidecar = build_minimal_sidecar(
            program_id=program.program_id,
            receipt_path=receipt_path,
            receipt_sig_path=receipt_path.with_suffix(".sig"),
            retrieval_modes=context.get("retrieval_modes", {}),
            traversal_path=[],
            skills_applied=context.get("skills_applied", []),
            token_cost=context.get("token_cost", {}),
        )
        sidecar["subgraph_node_ids"] = list(context.get("node_ids", []))
        sidecar["target_node_id"] = context.get("target_node_id")
        sidecar["enrichment_data_hash"] = context.get("enrichment_data_hash")
        write_sidecar(receipt_path.parent, program.program_id, sidecar, SidecarSigner(self.config.codebase_root))

    def _auto_rollback_regressed_skills(self, program: DiscoveredProgram) -> None:
        if self.config.no_graphrag or program.program_id not in self._graphrag_contexts:
            return
        from omnix.evolve.skill_bank import SkillBank

        db = self.config.codebase_root / ".omnix" / "omnix.db"
        store = GraphStore(str(db))
        try:
            rolled_back = SkillBank(store).auto_rollback_on_regression(
                store,
                runs_dir=self.run_state.run_dir.parent,
            )
            for skill_id in rolled_back:
                self.run_state.emit_event(
                    "skill_rolled_back",
                    {"program_id": program.program_id, "skill_id": skill_id},
                )
        except Exception as exc:
            self.run_state.emit_event(
                "skill_rollback_error",
                {"program_id": program.program_id, "error": f"{type(exc).__name__}: {exc}"},
            )
        finally:
            store.close()


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


def ensure_cobol_graph(codebase_root: Path, db_path: Path) -> GraphStore:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = GraphStore(str(db_path))
    if store.node_count() == 0:
        ingest_unified_codebase(str(codebase_root), store)
    return store


def resolve_graphrag_node_id(
    store: GraphStore,
    program_node_id: str,
    program_id: str,
    source_path: Path,
) -> str:
    if _node_exists(store, program_node_id):
        return program_node_id
    source_name = source_path.name
    for node in store.iter_all_nodes():
        if node.file_path and Path(node.file_path).name == source_name:
            return node.id
    needle = program_id.upper()
    for node in store.iter_all_nodes():
        if needle in node.name.upper() or needle in node.id.upper():
            return node.id
    return program_node_id


def _node_exists(store: GraphStore, node_id: str) -> bool:
    row = store.sqlite_connection().execute("SELECT 1 FROM nodes WHERE id = ? LIMIT 1", (node_id,)).fetchone()
    return row is not None


def _has_target_enrichment(store: GraphStore, target_node_id: str) -> bool:
    from omnix.enrich.common import get_node, has_enrichment

    target = get_node(store, target_node_id)
    if has_enrichment(target):
        return True
    return any(has_enrichment(neighbor) for neighbor in store.get_neighbors(target_node_id))


def _score_thought_against_failures(thought: str, gate6_failures: list[dict]) -> float:
    failure_text = json.dumps(gate6_failures, sort_keys=True).lower()
    thought_text = thought.lower()
    if "padding" in thought_text and (" " in failure_text or "padding" in failure_text):
        return 1.0
    if ("trailers" in thought_text or "file output" in thought_text) and (
        "\\n" in failure_text or "newline" in failure_text or "trailing" in failure_text
    ):
        return 0.8
    if "perform" in thought_text or "ordering" in thought_text:
        return 0.5
    return 0.25


def _gate6_failure_analysis_text(gate6_failures: list[dict]) -> str:
    from omnix.traversal.thought_mcts import format_failure_analysis_with_thought

    thought = next(
        (str(failure.get("mcts_thought")) for failure in gate6_failures if failure.get("mcts_thought")),
        None,
    )
    return format_failure_analysis_with_thought(gate6_failures, thought)


def _append_accuracy_boost_notes(prompt: str, gate6_failures: list[dict] | None) -> str:
    if not gate6_failures:
        return prompt
    thoughts = sorted({str(failure.get("mcts_thought")) for failure in gate6_failures if failure.get("mcts_thought")})
    if not thoughts:
        return prompt
    return prompt + "\n\nAccuracy-boost retry guidance:\n" + "\n".join(f"- {thought}" for thought in thoughts)


def _counts(rows: list[ProgramStateRow]) -> dict[str, int]:
    return {
        "verified": sum(1 for row in rows if row.state == "verified"),
        "gate6_failed": sum(1 for row in rows if row.state == "gate6_failed"),
        "skipped": sum(1 for row in rows if row.state == "skipped"),
        "error": sum(1 for row in rows if row.state == "error"),
    }


def print_summary(summary: AgentSummary) -> str:
    audit = str(summary.audit_zip) if summary.audit_zip is not None else "<none>"
    metrics = " ".join(f"{key}={value}" for key, value in sorted(summary.accuracy_boost_metrics.items()))
    return (
        f"Run {summary.run_id}\n"
        f"verified={summary.verified} gate6_failed={summary.gate6_failed} "
        f"skipped={summary.skipped} errored={summary.errored}\n"
        f"accuracy_boost={metrics or '<none>'}\n"
        f"receipts={summary.receipts_dir}\n"
        f"audit={audit}\n"
    )


def configure_copybook_path(copybook_paths: list[Path]) -> None:
    dirs = sorted({str(path.parent) for path in copybook_paths})
    if not dirs:
        return
    existing = os.environ.get("COBCPY")
    parts = [*dirs, *(existing.split(os.pathsep) if existing else [])]
    deduped = list(dict.fromkeys(part for part in parts if part))
    os.environ["COBCPY"] = os.pathsep.join(deduped)


def _reflexion_dispatch(gate6_failures: list[dict] | None) -> Callable[[str], str] | None:
    if not gate6_failures:
        return None

    def dispatch(prompt: str) -> str:
        refined = refine_prompt(
            ReflexionContext(
                original_prompt=prompt,
                failed_replica="",
                gate6_failures=gate6_failures,
            )
        )
        refined = _append_accuracy_boost_notes(refined, gate6_failures)
        return _default_llm_dispatch(refined)

    return dispatch
