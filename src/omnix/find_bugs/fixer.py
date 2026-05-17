"""
Layer 7: sandbox-only auto-fixer (P26). Signed receipts; user applies diffs (P27).
``--fix`` enables Fabric (P28). Sandbox is always removed in ``finally`` (P30).
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.axiom import keystore, sign

from . import fix_fabric, sandbox
from .test_detect import TestRunnerSpec, detect_test_runner, parse_pytest_summary

_LOG = logging.getLogger("omnix.find_bugs.fixer")
RECEIPT_DIR = Path.home() / ".omnix" / "receipts"
SECRET = Path.home() / ".omnix" / "keys" / "secret.pem"
PUB = Path.home() / ".omnix" / "keys" / "public.pem"


@dataclass
class FixOrchestraResult:
    success: bool
    receipt_path: str | None
    message: str
    body: dict[str, Any] = field(default_factory=dict)
    extra_finding: dict[str, Any] | None = None


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fingerprint() -> str:
    if not PUB.is_file():
        return ""
    return hashlib.sha256(PUB.read_bytes()).hexdigest()


def _json_canon(body: dict[str, Any]) -> bytes:
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _graph_n(graph_db: Path | None, rel: str) -> int:
    if not graph_db or not graph_db.is_file():
        return 0
    conn = sqlite3.connect(
        f"file:{graph_db}?mode=ro", uri=True, timeout=2.0
    )
    try:
        r = conn.execute(
            "SELECT count(*) FROM edges e JOIN nodes s ON s.id=e.source_id "
            "JOIN nodes t ON t.id=e.target_id "
            "WHERE s.file_path=? OR t.file_path=?",
            (rel, rel),
        ).fetchone()
        return int(r[0] or 0)
    finally:
        conn.close()


def run_test_suite_sandbox(
    sroot: Path, spec: TestRunnerSpec, tmo: float = 90.0
) -> dict[str, Any]:
    if not spec.command or spec.runner_id == "none":
        return {
            "exit": 1,
            "stdout": "",
            "stderr": "no test runner in sandbox",
            "pytest_passed": 0,
            "pytest_total": 0,
        }
    ppre = str(sroot) + (os.pathsep + os.environ.get("PYTHONPATH", ""))
    env2 = {**os.environ, "PYTHONPATH": ppre}
    r0 = subprocess.run(  # noqa: S603
        spec.command,
        cwd=str(sroot),
        capture_output=True,
        text=True,
        timeout=tmo,
        env=env2,
    )
    out, err = (r0.stdout or ""), (r0.stderr or "")
    passed, tot = 0, 0
    if spec.runner_id == "pytest":
        passed, tot = parse_pytest_summary(out, err)
    return {
        "exit": int(r0.returncode or 0),
        "stdout": out[:8000],
        "stderr": err[:8000],
        "pytest_passed": passed,
        "pytest_total": tot,
    }


def _suite_green(suite: dict[str, Any], spec: TestRunnerSpec) -> bool:
    c = int(suite.get("exit", 1) or 0)
    if spec.runner_id == "pytest" and c == 5:
        return False
    if spec.runner_id == "pytest" and c == 0:
        t = f"{suite.get('stdout', '')}{suite.get('stderr', '')}".lower()
        if "no tests ran" in t and "0 passed" in t:
            return False
        if "not found" in t and "file or directory" in t:
            return False
    return c == 0


def _unified(orig: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            orig.splitlines(),
            new.splitlines(),
            fromfile="a",
            tofile="b",
        )
    )


def _diff_hunk_metric(orig: str, new: str) -> int:
    n = 0
    for line in _unified(orig, new).splitlines():
        if not line or line[0] not in "+-":
            continue
        if line[:3] in ("---", "+++"):
            continue
        n += 1
    return n if n > 0 else 0


def _build_prompt(rel: str, fn0: str, orig_fail: dict[str, Any], src: str) -> str:
    p = f"Fix the Python function {fn0!r} in file {rel!r} so tests and PBT pass.\n"
    p += f"Original PBT/verify context (JSON): {json.dumps(orig_fail)[:12_000]}\n"
    p += f"--- source begin ---\n{src}\n--- source end ---\n"
    p += "Reply with JSON: {python_full_file: \"...entire .py file...\"}\n"
    return p


def _candidate_file_text(_orig: str, d: dict[str, Any]) -> str | None:
    t = d.get("python_full_file")
    if isinstance(t, str) and t.strip():
        return t
    u = d.get("unified_diff")
    if isinstance(u, str) and u.strip():
        _LOG.debug("unified_diff not applied; use python_full_file")
    return None


def _pbt_sandbox(
    sbox: Path,
    sbox_file: Path,
    fn0: str,
    graph_db: Path | None,
    tmo: float,
) -> bool:
    cmd = [
        sys.executable,
        "-m",
        "omnix.verify.cli",
        str(sbox_file.resolve()),
        "--function",
        fn0,
        "--examples",
        "2",
        "--no-receipt",
        "--json",
        "--codebase-root",
        str(sbox.resolve()),
    ]
    if graph_db and graph_db.is_file():
        cmd.extend(["--graph-db", str(graph_db.resolve())])
    ppre = str(sbox) + (os.pathsep + os.environ.get("PYTHONPATH", ""))
    env2 = {**os.environ, "PYTHONPATH": ppre}
    r0 = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(sbox),
        capture_output=True,
        text=True,
        timeout=tmo,
        env=env2,
    )
    return (r0.returncode or 0) == 0


def _write_receipt_pair(body: dict[str, Any]) -> str | None:
    if not SECRET.is_file():
        return None
    try:
        sk = keystore.secret_from_pem(SECRET.read_text(encoding="ascii"))
    except (OSError, ValueError) as e:
        _LOG.warning("code_fix: keystore: %s", e)
        return None
    b2 = {**body, "key_fp": _fingerprint()}
    raw = _json_canon(b2)
    try:
        sigb = sign.sign_bytes(sk, raw, b"", secrets.token_bytes(32))
    except ValueError as e:  # pragma: no cover
        _LOG.warning("code_fix: sign: %s", e)
        return None
    tflat = _iso_utc().replace(":", "-").replace(".", "-")
    fn0 = re.sub(
        r"[^A-Za-z0-9._-]+",
        "",
        str(body.get("function", "fn")),
    )[:48]
    jpath = RECEIPT_DIR / f"fix_{tflat}_{fn0}.json"
    spath = jpath.parent / f"{jpath.stem}.sig"
    jpath.parent.mkdir(parents=True, exist_ok=True)
    tmpj = jpath.parent / f".e_{jpath.name}.j"
    tmps = jpath.parent / f".e_{jpath.name}.s"
    tmpj.write_bytes(raw)
    tmps.write_text(keystore.signature_to_pem(sigb), encoding="ascii")
    tmpj.replace(jpath)
    tmps.replace(spath)
    return str(jpath)


def orchestrate_code_fix(  # noqa: PLR0911, PLR0912, PLR0915, C901
    *,
    repo_root: Path,
    rel_failing: str,
    function_name: str,
    language: str,
    original_failure: dict[str, Any],
    graph_db: Path | None,
    agent_id: str = "find_bugs",
) -> FixOrchestraResult:
    is_py = rel_failing.lower().endswith(".py") or (language or "").lower() in (
        "",
        "python",
        "py",
    )
    if not is_py:
        return FixOrchestraResult(
            False, None, "language_not_supported_5c", body={}
        )

    sb0: Path | None = None
    out_body: dict[str, Any] = {
        "kind": "code_fix",
        "schema_version": 1,
        "function": function_name,
        "language": "python",
        "file_path": rel_failing.replace("\\", "/"),
        "n_graph_edges": _graph_n(graph_db, rel_failing.replace("\\", "/")),
    }
    success = False
    message = "internal_error"

    try:
        fix_fabric.reset_code_fix_budget_for_tests()
        sb0 = sandbox.create_fix_sandbox()
        sandbox.assert_write_allowed(sb0 / "probe.txt")
        sandbox.copy_project_manifests(repo_root, sb0)
        sandbox.copy_shallow_test_artifacts(repo_root, sb0)
        sandbox.copy_file_into_sandbox(
            repo_root=repo_root, rel_path=rel_failing, sandbox_root=sb0
        )
        spec = detect_test_runner(sb0)
        out_body["test_runner"] = spec.runner_id
        out_body["order_chosen"] = list(spec.order_chosen)
        out_body["test_command"] = list(spec.command)

        baseline = run_test_suite_sandbox(sb0, spec)
        if not _suite_green(baseline, spec):
            out_body["status"] = "baseline_test_suite_failing"
            out_body["fix"] = {
                "diff": "",
                "lines_changed": 0,
                "candidates_tried": 0,
            }
            out_body["baseline"] = {
                "exit": baseline.get("exit"),
                "stderr": (baseline.get("stderr") or "")[:2000],
            }
            out_body["original_pbt_failure"] = original_failure
            message = "baseline_test_suite_failing"
            return FixOrchestraResult(  # noqa: TRY300
                False, None, message, body=out_body
            )

        sfile = (sb0 / rel_failing.replace("\\", "/")).resolve()
        if not sfile.is_file():
            out_body["status"] = "sandbox_path_missing"
            message = "sandbox_path_missing"
            return FixOrchestraResult(
                False, None, message, body=out_body
            )

        orig_text = sfile.read_text(encoding="utf-8", errors="replace")
        prompt = _build_prompt(
            rel_failing, function_name, original_failure, orig_text
        )
        best: tuple[str, int] | None = None
        n_tried = 0

        for _att in range(3):
            d, st, _raw = fix_fabric.request_code_fix(agent_id, prompt)
            if d is None:
                _LOG.debug("code_fix attempt: no payload (%s)", st)
                continue
            ctext = _candidate_file_text(orig_text, d)
            if not ctext:
                continue
            try:
                ast.parse(ctext)
            except SyntaxError as e:
                _LOG.debug("code_fix: syntax: %s", e)
                continue
            n_tried += 1
            sandbox.assert_write_allowed(sfile)
            sfile.write_text(ctext, encoding="utf-8")
            suite = run_test_suite_sandbox(sb0, spec)
            if not _suite_green(suite, spec):
                sfile.write_text(orig_text, encoding="utf-8")
                continue
            if not _pbt_sandbox(
                sb0, sfile, function_name, graph_db, 60.0
            ):
                sfile.write_text(orig_text, encoding="utf-8")
                continue
            sfile.write_text(orig_text, encoding="utf-8")
            m = _diff_hunk_metric(orig_text, ctext) or 1
            if best is None or m < best[1] or (
                m == best[1] and len(ctext) < len(best[0])
            ):
                best = (ctext, m)

        if not best:
            out_body["status"] = "unfixable"
            out_body["fix"] = {
                "diff": "",
                "lines_changed": 0,
                "candidates_tried": n_tried,
            }
            out_body["original_pbt_failure"] = original_failure
            message = "unfixable"
            return FixOrchestraResult(
                False, None, message, body=out_body
            )

        wtext, linem = best
        sfile.write_text(wtext, encoding="utf-8")
        udiff = _unified(orig_text, wtext)
        out_body["status"] = "suggested"
        out_body["fix"] = {
            "diff": udiff,
            "lines_changed": linem,
            "candidates_tried": n_tried,
        }
        out_body["original_pbt_failure"] = original_failure
        out_body["pbt_recheck"] = "passed"
        success = True
        message = (
            "A proposed fix is in the signed receipt; apply with git apply (P27), "
            "or merge the diff manually. The repo on disk was not modified (P26)."
        )
    except (OSError, ValueError, RuntimeError) as e:  # pragma: no cover
        _LOG.exception("code_fix orchestration failed")
        out_body["status"] = "orchestrate_error"
        out_body["error"] = f"{e!s}"[:2000]
    finally:
        if sb0 is not None:
            out_body["cleanup_succeeded"] = sandbox.cleanup_sandbox(sb0)
        else:
            out_body["cleanup_succeeded"] = True

    rstat = out_body.get("status")
    receipt: str | None = None
    if rstat in (
        "baseline_test_suite_failing",
        "unfixable",
        "suggested",
        "orchestrate_error",
        "sandbox_path_missing",
    ):
        receipt = _write_receipt_pair(out_body)

    return FixOrchestraResult(success, receipt, message, body=out_body)
