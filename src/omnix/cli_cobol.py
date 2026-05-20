"""COBOL CLI commands."""

from __future__ import annotations

import os
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
        ),
        run_state=state,
        decision_queue=queue,
    )
    try:
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
