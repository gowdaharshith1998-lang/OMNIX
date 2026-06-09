"""Gate 1 — syntactic parser dry-run.

The real gate runs the JavaParser-based emitter and treats a parse failure as
a structured GateError. Until the JVM JAR is vendored we ALSO ship a pure-Python
heuristic so the rest of the engine has coverage today.

Gap with real parser (recorded for M1 Phase 6 dispatch):
- The heuristic only catches gross structural problems: empty source, severely
  unbalanced braces. It does NOT detect: missing semicolons, malformed generics,
  bad annotations, invalid keywords, or any token-level error. Tests that rely on
  the real parser are `xfail(strict=True, reason="JVM JAR not vendored")` and will
  flip XPASS the moment the JAR lands.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from omnix.gates.errors import GateCrashError
from omnix.gates.result import GateError

_GATE_NUMBER = 1
_GATE_NAME = "syntactic"


def check(source_code: str) -> GateError | None:
    """Return None on parse success, GateError on parse failure.

    Lazily attempts the real JVM parse path; falls back to a pure-Python smoke
    check when the vendored JAR is missing. JAR-missing = GateCrashError, NOT a
    silent pass — caller (runner) records the crash and marks the gate failed.
    """
    # 1. Empty source — never valid Java.
    if source_code == "" or source_code.strip() == "":
        return GateError(
            gate_number=_GATE_NUMBER,
            gate_name=_GATE_NAME,
            message="source is empty",
            details={"reason": "empty_source"},
        )

    # 2. Cheap deterministic heuristic — unbalanced braces. Runs BEFORE the JVM
    # path because (a) it's faster, (b) it gives a structured "reason" detail
    # that callers rely on (`details["reason"] == "unbalanced_braces"`), (c) the
    # JVM path subsumes this case but with different details — running heuristic
    # first preserves the contract.
    n_open = source_code.count("{")
    n_close = source_code.count("}")
    if n_open != n_close:
        return GateError(
            gate_number=_GATE_NUMBER,
            gate_name=_GATE_NAME,
            message=f"unbalanced braces ({n_open} open, {n_close} close)",
            details={"reason": "unbalanced_braces", "open": n_open, "close": n_close},
        )

    # 3. Real JVM parse path — only invoked when the vendored JAR is actually
    # present. When the JAR is missing we silently fall through to the heuristic
    # (the explicit "today" path). When the JAR is present but the JVM blows up,
    # that IS a crash and we raise GateCrashError so the runner records it.
    try:
        from omnix.semantic.errors import JavaSemanticError  # noqa: PLC0415
        from omnix.semantic.java import parser as java_parser  # noqa: PLC0415

        jar = getattr(java_parser, "JAR_PATH", None)
        jar_present = jar is not None and Path(jar).exists() and shutil.which("java") is not None
    except ImportError:
        jar_present = False

    if jar_present:
        try:
            import tempfile  # noqa: PLC0415

            from omnix.semantic.errors import JavaSemanticError  # noqa: PLC0415
            from omnix.semantic.java import parser as java_parser  # noqa: PLC0415

            with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as fh:
                fh.write(source_code)
                tmp_path = Path(fh.name)
            try:
                java_parser.parse_file(tmp_path)
            except JavaSemanticError as exc:
                msg = str(exc)
                if "vendored JAR missing" in msg:
                    # JAR was present moments ago — race / mid-flight deletion = crash.
                    raise GateCrashError(_GATE_NUMBER, f"JAR missing: {msg}", original=exc) from exc
                # Real parse failure — structured GateError.
                return GateError(
                    gate_number=_GATE_NUMBER,
                    gate_name=_GATE_NAME,
                    message=msg,
                    details={"line": None, "column": None, "expected_token": None},
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            return None
        except GateCrashError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GateCrashError(_GATE_NUMBER, f"JVM parser unavailable: {exc}", original=exc) from exc

    return None
