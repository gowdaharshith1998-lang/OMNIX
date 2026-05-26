"""Subprocess entrypoint for the fenced transformer sandbox.

Reads a JSON payload ``{"source": ..., "input_value": ..., "input_kind": ...}``
from stdin, applies ``resource.setrlimit`` for CPU/AS/NOFILE, compiles the
source via RestrictedPython, exec's it under a strict ``safe_globals``, then
calls ``transform(input_value)`` and writes a JSON result to stdout.

Run as: ``python -u sandbox_runner.py``.
"""

from __future__ import annotations

import json
import os
import sys


def _apply_rlimits() -> None:
    """Apply CPU + AS + NOFILE rlimits. RLIMIT_CPU triggers SIGXCPU; RLIMIT_AS
    will cause allocation failures / SIGKILL on OOM."""
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return
    cpu_sec = int(os.environ.get("OMNIX_DM_SUBPROCESS_CPU_SEC", "5"))
    as_mb = int(os.environ.get("OMNIX_DM_SUBPROCESS_AS_MB", "256"))
    nofile = int(os.environ.get("OMNIX_DM_SUBPROCESS_NOFILE", "8"))
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_sec, cpu_sec))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (as_mb * 1024 * 1024, as_mb * 1024 * 1024)
        )
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    except (ValueError, OSError):
        pass


def _decode_input(input_value, input_kind):
    """Reverse the parent's ``_to_json_safe`` encoding so the transformer sees
    a real datetime / Decimal / etc.
    """
    import datetime
    import decimal

    if isinstance(input_value, dict):
        if "__datetime__" in input_value:
            return datetime.datetime.fromisoformat(input_value["__datetime__"])
        if "__date__" in input_value:
            return datetime.date.fromisoformat(input_value["__date__"])
        if "__decimal__" in input_value:
            return decimal.Decimal(input_value["__decimal__"])
        if "__bytes__" in input_value:
            return bytes.fromhex(input_value["__bytes__"])
    return input_value


def _encode_result(result):
    import datetime
    import decimal

    if isinstance(result, datetime.datetime):
        return {"__datetime__": result.isoformat()}
    if isinstance(result, datetime.date):
        return {"__date__": result.isoformat()}
    if isinstance(result, decimal.Decimal):
        return {"__decimal__": str(result)}
    if isinstance(result, (bytes, bytearray)):
        return {"__bytes__": bytes(result).hex()}
    if isinstance(result, (list, tuple)):
        return [_encode_result(x) for x in result]
    if isinstance(result, dict):
        return {str(k): _encode_result(v) for k, v in result.items()}
    return result


def main() -> int:  # pragma: no cover - exercised via subprocess.run
    _apply_rlimits()
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        sys.stdout.write(
            json.dumps({"kind": "error", "error_type": "PayloadDecode", "error_message": str(exc)})
        )
        return 0

    source = payload["source"]
    input_value = _decode_input(payload["input_value"], payload.get("input_kind", "repr"))

    # Make sure we route compilation through the same module the parent uses.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

    from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
        build_safe_globals,
        compile_safe,
    )

    try:
        bytecode = compile_safe(source)
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "kind": "error",
                    "error_type": "CompileFailure",
                    "error_message": str(exc),
                }
            )
        )
        return 0

    safe_globals = build_safe_globals()
    local_ns: dict = {}
    try:
        exec(bytecode, safe_globals, local_ns)
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "kind": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        )
        return 0

    fn = local_ns.get("transform") or safe_globals.get("transform")
    if fn is None:
        sys.stdout.write(
            json.dumps(
                {
                    "kind": "error",
                    "error_type": "MissingTransform",
                    "error_message": "no transform() defined in source",
                }
            )
        )
        return 0

    try:
        out = fn(input_value)
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "kind": "error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        )
        return 0

    sys.stdout.write(
        json.dumps(
            {
                "kind": "ok",
                "result": _encode_result(out),
                "result_repr": repr(out),
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
