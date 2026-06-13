"""Python bridge to the JavaParser-based semantic emitter.

Architecture (v1):
- Short-lived JVM subprocess per source file (matches `_run_verify_limited`
  isolation pattern). No long-running daemon, no JNI, no gRPC surface.
- Subprocess emits one JSON object per declared symbol to stdout, one per line.
  Each line is consumed by `SemanticNode.from_json`.
- All failures map to structured errors from `omnix.semantic.errors` — silent
  fallback to `Object`-typed nodes would poison downstream gate logic.

See `src/omnix/semantic/java/jvm/README.md` for how the JAR is built and
vendored. The JAR itself is not committed in this slice; tests that need it
are marked `xfail(strict=True)` so they flip XPASS the moment it lands.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from omnix.semantic.errors import (
    JavaSemanticError,
    JavaSemanticTimeoutError,
    UnresolvedSymbolError,
)
from omnix.semantic.node import SemanticNode

# Pinned location of the vendored emitter JAR. Build + vendor instructions:
# src/omnix/semantic/java/jvm/README.md. SHA256 pin: vendor/SHA256SUMS.
JAR_PATH: Path = Path(__file__).parent / "vendor" / "javaparser-emitter.jar"

# Well-known sentinel emitted by JavaSemanticEmitter on UnsolvedSymbolException.
# Format: "UnresolvedSymbol: <symbol>@<file>:<line> :: <message>"
# <file> is matched non-greedily up to the final ":<line> ::" so Windows
# drive-letter colons (C:\...) stay inside the file group.
_UNRESOLVED_RE = re.compile(
    r"UnresolvedSymbol:\s*(?P<symbol>[^@]+)@(?P<file>.+?):(?P<line>\d+)\s*::\s*(?P<message>.*)"
)


def parse_file(
    path: Path,
    classpath: list[Path] | None = None,
    timeout_s: float = 30.0,
) -> list[SemanticNode]:
    """Parse a Java source file into a list of SemanticNode.

    Args:
        path: source file to parse.
        classpath: optional list of JARs / class dirs for symbol resolution.
        timeout_s: wall-clock budget for the JVM subprocess.

    Returns:
        List of SemanticNode (one per top-level type + method declaration).

    Raises:
        JavaSemanticError: vendored JAR missing, generic subprocess failure,
            or malformed emitter output.
        UnresolvedSymbolError: emitter could not resolve a referenced symbol.
        JavaSemanticTimeoutError: subprocess exceeded `timeout_s`.
    """
    if not JAR_PATH.exists():
        raise JavaSemanticError(
            "vendored JAR missing — run scripts/vendor_javaparser.sh; "
            "see src/omnix/semantic/java/jvm/README.md"
        )
    if shutil.which("java") is None:
        raise JavaSemanticError(
            "java executable missing on PATH — install a JRE/JDK and rerun; "
            "see src/omnix/semantic/java/jvm/README.md"
        )

    argv: list[str] = ["java", "-jar", str(JAR_PATH), str(path)]
    if classpath:
        argv.extend(str(p) for p in classpath)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = _decode(exc.stderr)
        raise JavaSemanticTimeoutError(str(path), timeout_s, stderr) from exc
    except FileNotFoundError as exc:
        raise JavaSemanticError(
            "java executable missing on PATH — install a JRE/JDK and rerun; "
            "see src/omnix/semantic/java/jvm/README.md"
        ) from exc

    stdout = _decode(proc.stdout)
    stderr = _decode(proc.stderr)

    if proc.returncode != 0:
        match = _UNRESOLVED_RE.search(stderr)
        if match:
            raise UnresolvedSymbolError(
                symbol=match.group("symbol").strip(),
                file_path=match.group("file").strip(),
                line=int(match.group("line")),
                message=match.group("message").strip(),
            )
        raise JavaSemanticError(stderr or stdout or f"exit {proc.returncode}")

    nodes: list[SemanticNode] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            nodes.append(SemanticNode.from_json(line))
        except (ValueError, KeyError, TypeError) as exc:
            raise JavaSemanticError(
                f"malformed emitter output line: {line!r} ({exc})"
            ) from exc
    return nodes


def _decode(buf: bytes | str | None) -> str:
    """Best-effort decode of subprocess byte buffer to str."""
    if buf is None:
        return ""
    if isinstance(buf, str):
        return buf
    return buf.decode("utf-8", errors="replace")
