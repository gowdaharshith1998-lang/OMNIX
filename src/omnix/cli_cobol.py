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
