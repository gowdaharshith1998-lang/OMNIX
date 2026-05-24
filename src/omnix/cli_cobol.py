"""COBOL CLI commands."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click

from omnix.graph.store import GraphStore
from omnix.rebuild.cobol_runner import (
    CobolRebuildError,
    GateFailure,
    iter_cobol_programs,
    rebuild_cobol_program,
)
from omnix.receipts.finding_receipt import now_iso8601_utc
from omnix.runtime.cobol.capture import run_capture
from omnix.runtime.cobol.gnucobol_adapter import compile_cobol
from omnix.spec.cobol_hypothesis import generate_spec


@click.group("cobol")
def cobol_group() -> None:
    """COBOL substrate commands."""


@cobol_group.command("modernize")
@click.argument("codebase", required=False, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--target", "target_language", default="python", type=click.Choice(["python"]), show_default=True)
@click.option("--budget-usd", default=10.0, type=float, show_default=True)
@click.option("--max-retries", default=2, type=int, show_default=True)
@click.option("--auto-skip-no-fixtures", is_flag=True, default=False)
@click.option("--halt-on-failure", is_flag=True, default=False)
@click.option("--decision-timeout-s", default=60.0, type=float, show_default=True)
@click.option("--no-auto-audit", is_flag=True, default=False)
@click.option("--resume", "resume_run_id", default=None)
@click.option("--graphrag-token-budget", default=30000, type=int, show_default=True)
@click.option("--graphrag-hop-depth", default=4, type=int, show_default=True)
@click.option("--graphrag-max-turns", default=8, type=int, show_default=True)
@click.option("--graphrag-confidence-threshold", default=0.75, type=float, show_default=True)
@click.option("--graphrag-skill-top-k", default=3, type=int, show_default=True)
@click.option("--graphrag-model", default="claude-sonnet-4.6", show_default=True)
@click.option("--no-graphrag", is_flag=True, default=False)
@click.option("--accuracy-boost", is_flag=True, default=False)
def modernize_cmd(
    codebase: Path | None,
    target_language: str,
    budget_usd: float,
    max_retries: int,
    auto_skip_no_fixtures: bool,
    halt_on_failure: bool,
    decision_timeout_s: float,
    no_auto_audit: bool,
    resume_run_id: str | None,
    graphrag_token_budget: int,
    graphrag_hop_depth: int,
    graphrag_max_turns: int,
    graphrag_confidence_threshold: float,
    graphrag_skill_top_k: int,
    graphrag_model: str,
    no_graphrag: bool,
    accuracy_boost: bool,
) -> None:
    """Run the sequential COBOL modernization orchestrator."""
    from omnix.orchestrator.cobol.agent import AgentConfig, ModernizeAgent, print_summary
    from omnix.orchestrator.cobol.decision_queue import TerminalDecisionQueue
    from omnix.orchestrator.cobol.run_state import RunState

    if resume_run_id:
        state = RunState.resume(resume_run_id)
        root = state.codebase_root
    else:
        if codebase is None:
            raise click.UsageError("CODEBASE is required unless --resume is provided")
        root = codebase.resolve()
        state = RunState.create(root, target_language, budget_usd)
    queue = TerminalDecisionQueue(state)
    try:
        with _accuracy_boost_env(accuracy_boost):
            agent = ModernizeAgent(
                AgentConfig(
                    codebase_root=root,
                    target_language=target_language,
                    budget_usd=budget_usd,
                    max_gate6_retries=max_retries,
                    auto_skip_no_fixtures=auto_skip_no_fixtures,
                    halt_on_failure=halt_on_failure,
                    decision_timeout_s=decision_timeout_s,
                    no_auto_audit=no_auto_audit,
                    graphrag_token_budget=graphrag_token_budget,
                    graphrag_hop_depth=graphrag_hop_depth,
                    graphrag_max_turns=graphrag_max_turns,
                    graphrag_confidence_threshold=graphrag_confidence_threshold,
                    graphrag_skill_top_k=graphrag_skill_top_k,
                    graphrag_model=graphrag_model,
                    no_graphrag=no_graphrag,
                ),
                run_state=state,
                decision_queue=queue,
            )
            summary = agent.resume() if resume_run_id else agent.run()
            click.echo(print_summary(summary), err=True)
            if summary.gate6_failed or summary.errored:
                raise SystemExit(1)
            if summary.verified == 0 and summary.skipped > 0:
                raise SystemExit(1)
    except KeyboardInterrupt:
        click.echo(f"Run paused. Resume with: omnix cobol modernize --resume {state.run_id}", err=True)
        raise SystemExit(130)
    finally:
        state.close()


@contextmanager
def _accuracy_boost_env(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    updates = {
        "OMNIX_CHUNK_MODE": "auto",
        "OMNIX_GRAPHRAG_RERANK_MODE": "auto",
        "OMNIX_MCTS_MODE": "auto",
        "OMNIX_ESE_MODE": "auto",
    }
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@cobol_group.command("enrich")
@click.argument("codebase_root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--passes", "passes_text", default="1,2,3,4", show_default=True)
@click.option("--budget-usd", default=None, type=float)
@click.option("--batch-size", default=50, type=int, show_default=True)
@click.option("--force", is_flag=True, default=False)
@click.option("--mock/--live", "mock", default=False, show_default=True)
def enrich_cmd(
    codebase_root: Path,
    passes_text: str,
    budget_usd: float | None,
    batch_size: int,
    force: bool,
    mock: bool,
) -> None:
    """Run offline COBOL GraphRAG enrichment against the project graph."""
    from omnix.enrich.live_provider import OpenAIEnrichmentProvider
    from omnix.enrich.mock_provider import MockEnrichmentProvider
    from omnix.enrich.passes import run_passes
    from omnix.orchestrator.cobol.agent import ensure_cobol_graph

    root = codebase_root.resolve()
    db_path = root / ".omnix" / "omnix.db"
    store = ensure_cobol_graph(root, db_path)
    mock_provider = MockEnrichmentProvider() if mock else None
    provider = mock_provider if mock_provider is not None else OpenAIEnrichmentProvider()
    try:
        report = asyncio.run(
            run_passes(
                store,
                provider,
                passes_text,
                budget_usd=budget_usd,
                batch_size=batch_size,
                force=force,
            )
        )
        if mock_provider is not None:
            provider_label = "mock"
            extra = f" mock_calls={len(mock_provider.calls)}"
        else:
            provider_label = "openai"
            extra = ""
        click.echo(
            f"enriched passes={len(report.reports)} cost=${report.total_cost_usd:.4f} "
            f"provider={provider_label}{extra} db={db_path}"
        )
    finally:
        store.close()


@cobol_group.group("skills")
def skills_group() -> None:
    """Manage COBOL GraphRAG skill-bank entries."""


@skills_group.command("list")
@click.argument("codebase_root", required=False, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--invalid", "include_invalid", is_flag=True, default=False)
def skills_list_cmd(codebase_root: Path | None, include_invalid: bool) -> None:
    from omnix.enrich.common import graph_db_path
    from omnix.evolve.skill_bank import SkillBank

    root = (codebase_root or Path.cwd()).resolve()
    store = GraphStore(str(graph_db_path(root)))
    try:
        skills = SkillBank(store).list_all(include_invalid=include_invalid)
        if not skills:
            click.echo("No COBOL GraphRAG skills")
            return
        for skill in skills:
            status = "invalid" if skill.t_invalid else "active"
            click.echo(f"{skill.skill_id} v{skill.version} {status} {skill.title}")
    finally:
        store.close()


@skills_group.command("rollback")
@click.argument("skill_id")
@click.argument("codebase_root", required=False, type=click.Path(exists=True, file_okay=False, path_type=Path))
def skills_rollback_cmd(skill_id: str, codebase_root: Path | None) -> None:
    from omnix.enrich.common import graph_db_path
    from omnix.evolve.skill_bank import SkillBank

    root = (codebase_root or Path.cwd()).resolve()
    store = GraphStore(str(graph_db_path(root)))
    try:
        SkillBank(store).invalidate(skill_id, "manual rollback")
        click.echo(f"rolled back {skill_id}")
    finally:
        store.close()


@skills_group.command("review")
@click.argument("codebase_root", required=False, type=click.Path(exists=True, file_okay=False, path_type=Path))
def skills_review_cmd(codebase_root: Path | None) -> None:
    from omnix.enrich.common import graph_db_path
    from omnix.enrich.mock_provider import MockEnrichmentProvider
    from omnix.evolve.designer import run_designer
    from omnix.evolve.hard_case_buffer import HardCaseBuffer

    root = (codebase_root or Path.cwd()).resolve()
    store = GraphStore(str(graph_db_path(root)))
    provider = MockEnrichmentProvider()
    try:
        report = asyncio.run(run_designer(store, HardCaseBuffer(store), provider))
        click.echo(f"clusters={report.clusters_examined} skills_minted={report.skills_minted}")
    finally:
        store.close()


@cobol_group.command("decide")
@click.option("--run", "run_id", required=True)
@click.option("--decision", "decision_id", required=True)
@click.option("--answer", required=True)
def decide_cmd(run_id: str, decision_id: str, answer: str) -> None:
    """Answer a pending COBOL orchestrator decision."""
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.resume(run_id)
    try:
        state.answer_decision(decision_id, answer)
        click.echo(f"answered {decision_id}={answer}")
    finally:
        state.close()


@cobol_group.command("audit-export")
@click.argument("run_id")
@click.option("--out", "out_path", required=True, type=click.Path(path_type=Path))
@click.option("--include-replicas/--no-replicas", default=True, show_default=True)
def audit_export_cmd(run_id: str, out_path: Path, include_replicas: bool) -> None:
    """Export a shareable audit zip for a COBOL orchestrator run."""
    from omnix.orchestrator.cobol.audit_export import export_audit_zip
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.resume(run_id)
    try:
        out = export_audit_zip(run_state=state, out_path=out_path, include_replicas=include_replicas)
        click.echo(str(out.resolve()))
    finally:
        state.close()


@cobol_group.command("runs")
@click.option("--status", "status_filter", default=None)
def runs_cmd(status_filter: str | None) -> None:
    """List COBOL orchestrator runs."""
    from omnix.orchestrator.cobol.run_state import list_runs

    runs = list_runs(status=status_filter)
    if not runs:
        click.echo("No COBOL orchestrator runs")
        return
    for row in runs:
        click.echo(
            f"{row['run_id']}  status={row['status']}  target={row['target_lang']}  "
            f"spend=${float(row['total_spend_usd']):.2f}  root={row['codebase_root']}"
        )


@cobol_group.command("capture")
@click.argument("program", type=click.Path(exists=True, path_type=Path))
@click.option("--fixtures", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output", default=".omnix/captures/cobol", type=click.Path(path_type=Path))
@click.option("--timeout", default=10.0, type=float)
def capture_cmd(program: Path, fixtures: Path, output: Path, timeout: float) -> None:
    project_root = Path.cwd()
    out_dir = output / program.stem
    capture_program = program
    temp_dir = None
    if program.suffix.lower() in {".cob", ".cbl", ".cobol"}:
        import tempfile

        temp_dir = tempfile.TemporaryDirectory()
        capture_program = compile_cobol(program, out_dir=Path(temp_dir.name))
    res = run_capture(
        project_root=project_root,
        program=capture_program,
        fixtures_dir=fixtures,
        output_root=out_dir,
        timeout_s=timeout,
    )
    if temp_dir is not None:
        temp_dir.cleanup()
    click.echo(f"captured {len(res)} fixture(s) into {out_dir}")


@cobol_group.command("spec-gen")
@click.argument("program")
@click.option("--captures", default=".omnix/captures/cobol", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--out", default="tests/cobol/generated", type=click.Path(path_type=Path))
def spec_gen_cmd(program: str, captures: Path, out: Path) -> None:
    try:
        path = generate_spec(program, captures, out)
    except FileNotFoundError:
        raise SystemExit(2)
    click.echo(str(path))


@cobol_group.command("rebuild")
@click.argument("project_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--target",
    "target_language",
    default="python",
    type=click.Choice(["python"]),
    show_default=True,
)
@click.option("--node-filter", default=None, help="glob filter, e.g. '*TC011A*'")
def cobol_rebuild_cmd(
    project_path: Path,
    target_language: str,
    node_filter: str | None,
) -> None:
    """Rebuild COBOL programs as target-language replicas; emit RebuildReceipts."""
    root = project_path.resolve()
    db_path = root / ".omnix" / "omnix.db"
    if not db_path.is_file():
        click.echo(
            f"FAIL: graph not found at {db_path}; run batch ingest before cobol rebuild",
            err=True,
        )
        raise SystemExit(2)

    store = GraphStore(str(db_path))
    try:
        programs = iter_cobol_programs(store, root, node_filter=node_filter)
        if not programs:
            click.echo(
                f"FAIL: no COBOL programs matched node-filter={node_filter!r}",
                err=True,
            )
            raise SystemExit(2)
        ts = now_iso8601_utc().replace(":", "-")
        receipts_dir = Path(
            os.environ.get(
                "OMNIX_COBOL_RECEIPTS_DIR",
                str(root / ".omnix" / "receipts" / "cobol" / ts),
            )
        )
        outputs: list[Path] = []
        for program in programs:
            try:
                receipt = rebuild_cobol_program(
                    store=store,
                    program_node_id=program.node_id,
                    target_language=target_language,
                    receipts_dir=receipts_dir,
                    keystore=None,
                    llm_dispatch=None,
                    project_path=root,
                )
            except GateFailure as exc:
                click.echo(
                    f"FAIL: {program.name} gate={exc.gate_number} details={exc.details}",
                    err=True,
                )
                raise SystemExit(1) from exc
            except CobolRebuildError as exc:
                click.echo(f"FAIL: {program.name} rebuild: {exc}", err=True)
                raise SystemExit(1) from exc
            outputs.append(receipt)
            click.echo(f"OK {program.name} -> {receipt}")
        click.echo(f"{len(outputs)} COBOL receipt(s) written to {receipts_dir}")
    finally:
        store.close()
