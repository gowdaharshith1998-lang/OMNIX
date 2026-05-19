"""Python orchestrator for Gate 6 dual-runtime equivalence probes."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RUNNER_JAR: Path = (
    Path(__file__).resolve().parents[2]
    / "semantic"
    / "java"
    / "vendor"
    / "equivalence-probe-runner.jar"
)


@dataclass(frozen=True)
class ProbeResult:
    input: list[Any]
    legacy_outcome: str
    rebuilt_outcome: str
    wall_clock_bucket_legacy: str
    wall_clock_bucket_rebuilt: str
    stdout_legacy_sha256: str
    stdout_rebuilt_sha256: str
    stderr_legacy_sha256: str
    stderr_rebuilt_sha256: str
    return_value_legacy: Any
    return_value_rebuilt: Any
    exception_legacy: str | None
    exception_rebuilt: str | None


def run_harness(
    legacy_src: str,
    rebuilt_src: str,
    class_name: str,
    method_name: str,
    probe_inputs: list[list[Any]],
    *,
    parameter_types: list[str] | None = None,
    timeout_s: float = 60.0,
) -> list[ProbeResult]:
    """Run each probe in isolated JVM subprocesses for legacy and rebuilt source."""
    if parameter_types is None:
        parameter_types = ["java.lang.String"] if probe_inputs and probe_inputs[0] else []

    results: list[ProbeResult] = []
    for probe in probe_inputs:
        legacy = _run_side(
            source=legacy_src,
            class_name=class_name,
            method_name=method_name,
            parameter_types=parameter_types,
            probe=probe,
            timeout_s=timeout_s,
        )
        rebuilt = _run_side(
            source=rebuilt_src,
            class_name=class_name,
            method_name=method_name,
            parameter_types=parameter_types,
            probe=probe,
            timeout_s=timeout_s,
        )
        results.append(
            ProbeResult(
                input=list(probe),
                legacy_outcome=str(legacy["outcome"]),
                rebuilt_outcome=str(rebuilt["outcome"]),
                wall_clock_bucket_legacy=str(legacy["wall_clock_bucket"]),
                wall_clock_bucket_rebuilt=str(rebuilt["wall_clock_bucket"]),
                stdout_legacy_sha256=str(legacy["stdout_sha256"]),
                stdout_rebuilt_sha256=str(rebuilt["stdout_sha256"]),
                stderr_legacy_sha256=str(legacy["stderr_sha256"]),
                stderr_rebuilt_sha256=str(rebuilt["stderr_sha256"]),
                return_value_legacy=legacy.get("return_value"),
                return_value_rebuilt=rebuilt.get("return_value"),
                exception_legacy=legacy.get("exception"),
                exception_rebuilt=rebuilt.get("exception"),
            )
        )
    return results


def _run_side(
    *,
    source: str,
    class_name: str,
    method_name: str,
    parameter_types: list[str],
    probe: list[Any],
    timeout_s: float,
) -> dict[str, Any]:
    payload = {
        "source": source,
        "class_name": class_name,
        "method_name": method_name,
        "parameter_types": parameter_types,
        "probe": probe,
    }
    try:
        proc = subprocess.run(
            ["java", "-jar", str(_RUNNER_JAR)],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "outcome": "timeout",
            "wall_clock_bucket": "timeout",
            "stdout_sha256": _EMPTY_SHA256,
            "stderr_sha256": _EMPTY_SHA256,
            "return_value": None,
            "exception": f"timeout after {timeout_s:g}s",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }

    if proc.returncode != 0:
        return {
            "outcome": "runtime_crash",
            "wall_clock_bucket": "crash",
            "stdout_sha256": _EMPTY_SHA256,
            "stderr_sha256": _EMPTY_SHA256,
            "return_value": None,
            "exception": f"exit {proc.returncode}",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "outcome": "runtime_crash",
            "wall_clock_bucket": "crash",
            "stdout_sha256": _EMPTY_SHA256,
            "stderr_sha256": _EMPTY_SHA256,
            "return_value": None,
            "exception": "malformed runner output",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    if not isinstance(parsed, dict):
        raise TypeError("probe runner output must be a JSON object")
    return parsed


_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
