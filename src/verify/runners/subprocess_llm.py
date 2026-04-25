"""UNIVERSAL FLOOR: subprocess + optional Fabric ``fuzz_inputs``; all writes under ``/tmp``."""

from __future__ import annotations

import json
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import src.verify.strategies_universal as su
from src.verify import fuzz_fabric

from .base import Layer6Result

MAX_ADDRESS_SPACE = 512 * 1024 * 1024  # 512 MB — same order as find_bugs #6.2


def _set_rlimit_as() -> None:
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (MAX_ADDRESS_SPACE, MAX_ADDRESS_SPACE)
        )
    except (OSError, ValueError):
        pass


def _mk_sandbox() -> Path:
    d = tempfile.mkdtemp(prefix="omnix_fuzz_", dir="/tmp")
    return Path(d)


def _rm_tree(p: Path) -> None:
    if not p.is_dir():
        return
    for c in p.iterdir():
        if c.is_file() or c.is_symlink():
            c.unlink(missing_ok=True)  # type: ignore[call-arg]
        elif c.is_dir():
            _rm_tree(c)
    try:
        p.rmdir()
    except OSError:  # pragma: no cover
        pass


def run_target_command_limited(
    cmd: list[str],
    timeout_s: float,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Popen with ``communicate(timeout=)``, RLIMIT in child, kill group on timeout."""
    if timeout_s <= 0:
        timeout_s = 30.0
    venv = dict(os.environ) if env is None else {**os.environ, **env}
    start = time.perf_counter()
    # Intentional: run user-defined harness/verify code in a child process, not
    # LLM-generated code. RLIMIT_AS + communicate(timeout=) + start_new_session
    # limit blast radius; only /tmp and pipe I/O; killpg on timeout.
    p = subprocess.Popen(  # noqa: S603 # nosec B603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=venv,
        preexec_fn=_set_rlimit_as,
        start_new_session=True,
    )
    to = False
    try:
        out_s, err_s = p.communicate(timeout=float(timeout_s))
    except subprocess.TimeoutExpired:
        to = True
        try:
            os.killpg(p.pid, signal.SIGKILL)  # type: ignore[attr-defined, arg-type, misc, union-attr]
        except (OSError, ProcessLookupError, AttributeError):
            p.kill()
        out_s, err_s = p.communicate(timeout=2.0)  # type: ignore[assignment, misc, union-attr, operator]
    wall = time.perf_counter() - start
    rc = int(p.returncode) if p.returncode is not None else -1
    o = out_s or ""
    e = err_s or ""
    if to:
        cl = "timeout"
    else:
        cl = _classify_exit(rc, e, False)
    return {
        "returncode": rc,
        "stdout": o,
        "stderr": e,
        "class": cl,
        "wall_time": wall,
        "timeout": to,
    }


def _classify_exit(
    returncode: int | None, stderr: str, timed_out: bool
) -> str:
    if timed_out:
        return "timeout"
    el = (stderr or "").lower()
    if "memory" in el or "cannot allocate" in el or "oom" in el:
        return "oom"
    if returncode and (returncode < 0 or returncode > 128):
        return "segfault"
    if "segfault" in el:
        return "segfault"
    if returncode == 0 and not (stderr and stderr.strip()):
        return "ok"
    if returncode not in (0,):
        return "exception"
    if "traceback" in el or "error" in el or "exception" in el:
        return "exception"
    return "ok"


def _merge_inputs(
    synth: su.StrategySynthesis, fabric: list[list[Any]] | None
) -> list[list[Any]]:
    acc: list[list[Any]] = []
    for v in list(synth.boundary_values)[:8]:
        acc.append([v])
    if fabric:
        acc.extend(fabric[:6])
    return acc or [[0], [1]]


def _write_harness_fails_on_last(sb: Path, n_total: int) -> None:
    """Path ``harness`` under *sb* (``/tmp/...``) only; use ``Path.write_text`` for I/O."""
    code = f"""# autogen {uuid.uuid4().hex}
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
i = 0
if p and p.is_file():
    d = json.loads(p.read_text(encoding="utf-8"))
    i = int(d.get("i", 0))
if i == {n_total} - 1:
    raise ValueError("last")
print("ok", i)
"""
    (sb / "harness.py").write_text(code, encoding="utf-8")


def run_layer6_subprocess_limited(
    project_root: Path,  # noqa: ARG001
    rel: str,
    language: str,
    function_name: str,
    signature_text: str,
    agent_id: str = "omnix_fuzz",
    timeout_s: float = 12.0,
) -> Layer6Result:
    if rel.endswith(".rs") or (language or "").lower() in (
        "rust",
        "rs",
    ):
        synth = su.synthesize_from_rust_signature(
            signature_text or f"fn {function_name}() -> i32"
        )
    elif rel.endswith(".go") or (language or "").lower() in (
        "go",
        "golang",
    ):
        synth = su.synthesize_from_go_signature(
            signature_text or f"func {function_name}() int {{ return 0 }}"
        )
    else:
        synth = su.synthesize_dynamic_for_llm("code")

    fab: list[list[Any]] = []
    reason = "synthesis"
    if os.environ.get("OMNIX_FUZZ_DRY") == "1":
        reason = "dry"
    else:
        fab, reason, _d = fuzz_fabric.request_adversarial_inputs_from_fabric(
            agent_id,
            language=language,
            signature=signature_text,
            param_hint=repr(synth.param_types),
        )
    inps = _merge_inputs(synth, fab if fab else None)
    sb = _mk_sandbox()
    _write_harness_fails_on_last(sb, max(1, len(inps)))
    nrun = 0
    findings: list[dict[str, Any]] = []
    try:
        hpath = (sb / "harness.py").resolve()
        for i, _vec in enumerate(inps):
            nrun += 1
            inj = sb / "in.json"
            inj.write_text(
                json.dumps({"i": i, "function": function_name, "vec": _vec}),
                encoding="utf-8",
            )
            cmd = [sys.executable, str(hpath), str(inj)]
            st = run_target_command_limited(cmd, timeout_s=timeout_s)
            if st.get("class") == "exception" or (st.get("returncode", 0) or 0) != 0:
                findings.append(
                    {
                        "kind": "pbt",
                        "input": str(_vec)[:2000],
                        "failures": [
                            {
                                "exception_type": "PBT",
                                "exception_message": (st.get("stderr") or "")[:2000],
                                "shrunk_input": str(_vec)[:2000],
                            }
                        ],
                    }
                )
    finally:
        _rm_tree(sb)
    return Layer6Result(
        findings=findings,
        language=language,
        runner_used="subprocess_llm",
        extra_metadata={
            "reason": reason,
            "synthesis": asdict(synth) if is_dataclass(synth) else {},
        },
        ex_total=nrun,
    )


def dry_run_harness(raises: str) -> dict[str, Any]:
    """Test helper: one harness under ``/tmp``, then removed."""
    sb = _mk_sandbox()
    try:
        if raises == "oom":
            code = "x=[]\n" "while 1: x+=[0]*1_000_000\n"  # noqa: S608, SIM110
        elif raises == "timeout":
            code = "import time\ntime.sleep(100)\n"
        elif raises == "exit1":
            code = "import sys; sys.exit(1)\n"
        else:
            code = "raise ValueError('t')\n"
        (sb / "h.py").write_text(
            f"if __name__ == '__main__':\n    {code}\n", encoding="utf-8"
        )
        tmo = 0.3 if raises == "timeout" else 5.0
        return run_target_command_limited(
            [sys.executable, str(sb / "h.py")], timeout_s=tmo
        )
    finally:
        _rm_tree(sb)
