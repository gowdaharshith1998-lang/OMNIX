"""COBOL rebuild runner.

This module is intentionally parallel to :mod:`omnix.rebuild.runner`: the Java
M1 path remains unchanged, while COBOL gets its own source discovery, prompt,
Python target gates, real GnuCOBOL execution, and receipt emission.
"""

from __future__ import annotations

import ast
import base64
import fnmatch
import hashlib
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnix.fabric.dispatcher import dispatch as fabric_dispatch
from omnix.graph.store import GraphStore, NodeRow
from omnix.receipts.finding_keys import ensure_project_key
from omnix.receipts.finding_receipt import compute_project_id, now_iso8601_utc
from omnix.receipts.rebuild_receipt import (
    GATE_NAMES,
    GateResult,
    RebuildReceipt,
    sha256_hex_text,
    sign_rebuild,
)
from omnix.runtime.cobol.gnucobol_adapter import compile_cobol, run_cobol

PROMPT_TEMPLATE_VERSION = "cobol-m0-python-2026-05-19"


class CobolRebuildError(RuntimeError):
    """Base COBOL rebuild error."""


class MissingLlmCredentialsError(CobolRebuildError):
    """Raised when no real LLM credential is configured."""


class GateFailure(CobolRebuildError):
    def __init__(self, gate_number: int, details: dict[str, Any]) -> None:
        self.gate_number = gate_number
        self.details = details
        super().__init__(f"Gate {gate_number} failed: {details}")


@dataclass(frozen=True)
class CobolProgram:
    node_id: str
    name: str
    source_path: Path
    source_text: str


LlMDispatch = Callable[[str], str]


def iter_cobol_programs(
    store: GraphStore,
    project_path: Path,
    *,
    node_filter: str | None = None,
) -> list[CobolProgram]:
    """Return COBOL programs from semantic nodes, falling back to module nodes."""
    candidates: list[NodeRow] = [
        n for n in store.iter_all_nodes() if n.type in {"CobolProgram", "CobolModule"}
    ]
    out: list[CobolProgram] = []
    seen: set[str] = set()
    for node in candidates:
        if not node.file_path:
            continue
        source = _resolve_source(project_path, node.file_path)
        if source.suffix.lower() not in {".cob", ".cbl", ".cobol"}:
            continue
        name = _program_name(source, source.read_text(encoding="utf-8", errors="replace"))
        node_id = node.id if node.type == "CobolProgram" else f"{source.as_posix()}::CobolProgram::{name}"
        if node_filter and not (
            fnmatch.fnmatchcase(node_id, node_filter)
            or fnmatch.fnmatchcase(name, node_filter)
            or fnmatch.fnmatchcase(source.name, node_filter)
        ):
            continue
        key = source.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        text = source.read_text(encoding="utf-8", errors="replace")
        out.append(CobolProgram(node_id=node_id, name=name, source_path=source, source_text=text))
    return out


def rebuild_cobol_program(
    *,
    store: GraphStore,
    program_node_id: str,
    target_language: str,
    receipts_dir: Path,
    keystore: Any = None,
    llm_dispatch: LlMDispatch | None = None,
    project_path: Path | None = None,
) -> Path:
    """Rebuild one COBOL program to a Python replica and emit a signed receipt."""
    _ = keystore
    if target_language != "python":
        raise ValueError("COBOL M0 supports only --target python")
    root = (project_path or Path.cwd()).resolve()
    program = _load_program_by_id(store, root, program_node_id)
    captures = _load_capture_manifests(root, program.name)
    prompt = _build_prompt(program, captures, target_language)
    model = _active_model() if llm_dispatch is None else "injected"
    dispatch_fn = llm_dispatch or _default_llm_dispatch
    rebuilt = _ensure_python_harness(_extract_python_source(dispatch_fn(prompt)))

    gate_results = _run_gates(program, rebuilt, captures)
    for gate in gate_results:
        if gate.status != "passed":
            raise GateFailure(gate.gate_number, gate.details)

    ensure_project_key(root)
    project_id = compute_project_id(root)
    spec_hash = hashlib.sha256(
        json.dumps(
            {
                "program": program.name,
                "target_language": target_language,
                "captures": captures,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    receipt = RebuildReceipt(
        project_id=project_id,
        node_fqn=program.node_id,
        target_language=target_language,
        legacy_source_sha256=sha256_hex_text(program.source_text),
        rebuilt_source_sha256=sha256_hex_text(rebuilt),
        spec_hash=spec_hash,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash=sha256_hex_text(prompt),
        model=model,
        gate_results=tuple(gate_results),
        timestamp=now_iso8601_utc(),
        omnix_version=_omnix_version(),
    )
    receipts_dir.mkdir(parents=True, exist_ok=True)
    source_path = receipts_dir / f"{program.name}.py"
    receipt_path = receipts_dir / f"{program.name}.json"
    sig_path = receipts_dir / f"{program.name}.sig"
    source_path.write_text(rebuilt, encoding="utf-8")
    receipt_path.write_bytes(receipt.canonical_json())
    sig_path.write_text(sign_rebuild(receipt) + "\n", encoding="utf-8")
    return receipt_path


def _load_program_by_id(store: GraphStore, project_path: Path, program_node_id: str) -> CobolProgram:
    for program in iter_cobol_programs(store, project_path):
        if program.node_id == program_node_id:
            return program
    raise CobolRebuildError(f"COBOL program node not found: {program_node_id}")


def _resolve_source(project_path: Path, file_path: str) -> Path:
    p = Path(file_path)
    return p if p.is_absolute() else project_path / p


def _program_name(path: Path, text: str) -> str:
    m = re.search(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", text, flags=re.IGNORECASE)
    return (m.group(1) if m else path.stem).upper()


def _load_capture_manifests(project_path: Path, program_name: str) -> list[dict[str, Any]]:
    root = project_path / ".omnix" / "captures" / "cobol" / program_name
    if not root.is_dir():
        raise CobolRebuildError(f"NoCapturesAvailable: {root}")
    manifests = []
    for p in sorted(root.glob("*.json")):
        manifests.append(json.loads(p.read_text(encoding="utf-8")))
    if not manifests:
        raise CobolRebuildError(f"NoCapturesAvailable: {root}")
    for m in manifests:
        if "stdin_b64" not in m or "stdout_b64" not in m:
            raise CobolRebuildError(
                f"capture manifest {m.get('fixture_id', '<unknown>')} lacks stdin/stdout bytes; rerun capture"
            )
    return manifests


def _build_prompt(program: CobolProgram, captures: list[dict[str, Any]], target_language: str) -> str:
    samples = [
        {
            "fixture_id": c["fixture_id"],
            "stdin_b64": c["stdin_b64"],
            "stdout_b64": c["stdout_b64"],
            "exit_code": c["exit_code"],
        }
        for c in captures
    ]
    return (
        "Return ONLY Python source code. No markdown fences.\n"
        "Implement a function exactly named main(stdin: bytes) -> bytes.\n"
        "The function must reproduce the externally observable stdout bytes of the COBOL program.\n"
        "Do not read files, write files, import network libraries, or inspect environment variables.\n"
        f"Target language: {target_language}\n\n"
        f"COBOL program name: {program.name}\n"
        f"COBOL source:\n{program.source_text}\n\n"
        f"Captured I/O JSON:\n{json.dumps(samples, indent=2, sort_keys=True)}\n"
    )


def _default_llm_dispatch(prompt: str) -> str:
    provider, key = _provider_key_from_env()
    model = _model_for_provider(provider)
    payload = {
        "agent_id": "omnix-cobol-rebuild",
        "task_kind": "rebuild",
        "provider_key": {"provider": provider, "key": key},
        "options": {
            "provider_override": provider,
            "model_override": model,
            "timeout_ms": 120_000,
            "max_tokens": 4096,
        },
        "messages": [{"role": "user", "content": prompt}],
    }
    out = fabric_dispatch(payload)
    if not isinstance(out, dict) or not out.get("ok"):
        raise CobolRebuildError(f"fabric dispatch failed: {(out or {}).get('error', 'unknown')}")
    content = out.get("content")
    if not isinstance(content, str) or not content.strip():
        raise CobolRebuildError("fabric dispatch returned empty content")
    return content


def _provider_key_from_env() -> tuple[str, str]:
    choices = (
        ("openai", "OMNIX_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("google", "GOOGLE_API_KEY"),
    )
    for provider, env_name in choices:
        value = os.environ.get(env_name)
        if value:
            return provider, value
    raise MissingLlmCredentialsError(
        "COBOL rebuild requires LLM credentials. Set OMNIX_API_KEY or configure provider via `omnix providers detect`."
    )


def _active_model() -> str:
    provider, _key = _provider_key_from_env()
    return _model_for_provider(provider)


def _model_for_provider(provider: str) -> str:
    explicit = os.environ.get("OMNIX_COBOL_MODEL")
    if explicit:
        return explicit
    if provider == "anthropic":
        return "claude-haiku-4-5"
    if provider == "google":
        return "gemini-2.5-flash"
    return "gpt-4o"


def _extract_python_source(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:python)?\s*(.*?)```", t, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip() + "\n"
    return t + "\n"


def _ensure_python_harness(source: str) -> str:
    if "def main(" not in source:
        raise GateFailure(3, {"reason": "missing_main", "expected": "main(stdin: bytes) -> bytes"})
    if 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source:
        return source
    return (
        source.rstrip()
        + "\n\n"
        + "if __name__ == \"__main__\":\n"
        + "    import sys\n"
        + "    _out = main(sys.stdin.buffer.read())\n"
        + "    if isinstance(_out, str):\n"
        + "        _out = _out.encode()\n"
        + "    sys.stdout.buffer.write(_out or b\"\")\n"
    )


def _run_gates(program: CobolProgram, rebuilt: str, captures: list[dict[str, Any]]) -> list[GateResult]:
    gates = [
        _gate1_python_syntax(rebuilt),
        _gate2_python_compile(rebuilt),
        _gate3_external_signature(rebuilt),
        _gate4_dependency_allowlist(rebuilt),
        _gate5_generated_spec(program),
        _gate6_behavioral(program, rebuilt, captures),
    ]
    return gates


def _receipt_gate(gate_number: int, passed: bool, details: dict[str, Any]) -> GateResult:
    details = dict(details)
    if gate_number in {5, 6}:
        details["implemented_by"] = "cobol_runner"
    return GateResult(
        gate_number=gate_number,
        gate_name=GATE_NAMES[gate_number],
        status="passed" if passed else "failed",
        details=details,
    )


def _gate1_python_syntax(source: str) -> GateResult:
    try:
        ast.parse(source)
        return _receipt_gate(1, True, {})
    except SyntaxError as exc:
        return _receipt_gate(1, False, {"reason": "syntax_error", "line": exc.lineno, "message": exc.msg})


def _gate2_python_compile(source: str) -> GateResult:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "replica.py"
        path.write_text(source, encoding="utf-8")
        try:
            py_compile.compile(str(path), doraise=True)
            return _receipt_gate(2, True, {})
        except py_compile.PyCompileError as exc:
            return _receipt_gate(2, False, {"reason": "py_compile_error", "message": str(exc)})


def _gate3_external_signature(source: str) -> GateResult:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            argc = len(node.args.args)
            return _receipt_gate(3, argc == 1, {"expected": "main(stdin: bytes) -> bytes", "arg_count": argc})
    return _receipt_gate(3, False, {"expected": "main(stdin: bytes) -> bytes", "actual": None})


def _gate4_dependency_allowlist(source: str) -> GateResult:
    allowed = {"base64", "decimal", "math", "re", "struct", "sys"}
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    extra = sorted(i for i in imports if i not in allowed)
    return _receipt_gate(4, not extra, {"imports": sorted(imports), "extra": extra})


def _gate5_generated_spec(program: CobolProgram) -> GateResult:
    spec = Path("tests") / "cobol" / "generated" / f"test_{program.name}_spec.py"
    if not spec.is_file():
        return _receipt_gate(5, False, {"reason": "generated_spec_missing", "path": str(spec)})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(spec), "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    return _receipt_gate(
        5,
        proc.returncode == 0,
        {"path": str(spec), "returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]},
    )


def _gate6_behavioral(program: CobolProgram, rebuilt: str, captures: list[dict[str, Any]]) -> GateResult:
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        exe = compile_cobol(program.source_path, out_dir=temp)
        py_path = temp / f"{program.name.lower()}_replica.py"
        py_path.write_text(rebuilt, encoding="utf-8")
        failures: list[dict[str, Any]] = []
        for capture in captures:
            stdin_b = base64.b64decode(str(capture["stdin_b64"]), validate=True)
            legacy = run_cobol(exe, stdin_bytes=stdin_b, cwd=temp)
            captured_stdout = base64.b64decode(str(capture["stdout_b64"]), validate=True)
            if legacy.stdout != captured_stdout:
                failures.append(
                    {
                        "fixture_id": capture.get("fixture_id"),
                        "reason": "current COBOL output differs from captured manifest",
                        "captured_stdout_sha256": hashlib.sha256(captured_stdout).hexdigest(),
                        "legacy_stdout_sha256": hashlib.sha256(legacy.stdout).hexdigest(),
                        "captured_stdout": captured_stdout.decode("utf-8", errors="replace"),
                        "legacy_stdout": legacy.stdout.decode("utf-8", errors="replace"),
                    }
                )
                continue
            candidate = subprocess.run(
                [sys.executable, str(py_path)],
                input=stdin_b,
                capture_output=True,
                check=False,
                timeout=10.0,
            )
            if legacy.stdout != candidate.stdout or legacy.returncode != candidate.returncode:
                failures.append(
                    {
                        "fixture_id": capture.get("fixture_id"),
                        "legacy_exit": legacy.returncode,
                        "candidate_exit": candidate.returncode,
                        "legacy_stdout_sha256": hashlib.sha256(legacy.stdout).hexdigest(),
                        "candidate_stdout_sha256": hashlib.sha256(candidate.stdout).hexdigest(),
                        "legacy_stdout": legacy.stdout.decode("utf-8", errors="replace"),
                        "candidate_stdout": candidate.stdout.decode("utf-8", errors="replace"),
                    }
                )
        return _receipt_gate(6, not failures, {"fixtures": len(captures), "failures": failures})


def _omnix_version() -> str:
    try:
        from omnix.omnix_version import __version__ as version

        return str(version)
    except Exception:
        return "0.0.0"
