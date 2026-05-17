"""Gate 2 — type / symbol resolution.

Real implementation runs the JavaParser SymbolSolver pass and reports the first
unresolvable reference as a structured GateError. Until the JAR is vendored we
ship a pure-Python smoke check that flags malformed import FQNs only.

Gap with real parser (recorded for M1 Phase 6 dispatch):
- The heuristic only checks that import targets look like syntactically valid FQNs.
  It does NOT verify the target actually exists on the classpath, nor does it catch
  type errors inside method bodies (wrong argument types, undefined variables,
  missing fields, etc.). Tests covering real-parser behavior are
  `xfail(strict=True)` until the JAR lands.
"""

from __future__ import annotations

import re
from pathlib import Path

from omnix.gates.errors import GateCrashError
from omnix.gates.result import GateError

_GATE_NUMBER = 2
_GATE_NAME = "typecheck"

# Java import statement (single-type or on-demand). Captures the FQN; we strip
# the trailing `.*` for on-demand imports before validating.
_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([^;\s]+)\s*;\s*$", re.MULTILINE)
_FQN_RE = re.compile(r"^[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$*][\w$]*)*$")


def check(source_code: str, classpath: list[Path] | None = None) -> GateError | None:
    """Return None on full type-resolution success, GateError on first failure."""
    # 1. Real JVM symbol-solver path — only invoked when the vendored JAR is
    # actually present. Missing JAR falls through to the heuristic; mid-flight
    # JVM failures raise GateCrashError so the runner records them.
    try:
        from omnix.semantic.java import parser as java_parser  # noqa: PLC0415

        jar = getattr(java_parser, "JAR_PATH", None)
        jar_present = jar is not None and Path(jar).exists()
    except ImportError:
        jar_present = False

    if jar_present:
        try:
            import tempfile  # noqa: PLC0415

            from omnix.semantic.errors import (  # noqa: PLC0415
                JavaSemanticError,
                UnresolvedSymbolError,
            )
            from omnix.semantic.java import parser as java_parser  # noqa: PLC0415

            with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as fh:
                fh.write(source_code)
                tmp_path = Path(fh.name)
            try:
                java_parser.parse_file(tmp_path, classpath=classpath)
            except UnresolvedSymbolError as exc:
                return GateError(
                    gate_number=_GATE_NUMBER,
                    gate_name=_GATE_NAME,
                    message=str(exc),
                    details={
                        "unresolvable_type": exc.symbol,
                        "source_line": exc.line,
                        "context": "unknown",
                    },
                )
            except JavaSemanticError as exc:
                if "vendored JAR missing" in str(exc):
                    raise GateCrashError(_GATE_NUMBER, f"JAR missing: {exc}", original=exc) from exc
                return GateError(
                    gate_number=_GATE_NUMBER,
                    gate_name=_GATE_NAME,
                    message=str(exc),
                    details={
                        "unresolvable_type": None,
                        "source_line": None,
                        "context": "unknown",
                    },
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            return None
        except GateCrashError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GateCrashError(_GATE_NUMBER, f"JVM parser unavailable: {exc}", original=exc) from exc

    # 2. Pure-Python heuristic: import FQN sanity check.
    for match in _IMPORT_RE.finditer(source_code):
        raw_fqn = match.group(1).strip()
        check_fqn = raw_fqn[:-2] if raw_fqn.endswith(".*") else raw_fqn
        if not _FQN_RE.match(check_fqn) and check_fqn != "":
            # Compute source line. match.start(1) is the position of the FQN
            # capture group, which is the most reliable anchor.
            line = source_code[: match.start(1)].count("\n") + 1
            return GateError(
                gate_number=_GATE_NUMBER,
                gate_name=_GATE_NAME,
                message=f"malformed import FQN: {raw_fqn!r}",
                details={
                    "unresolvable_type": raw_fqn,
                    "source_line": line,
                    "context": "import",
                },
            )

    return None
