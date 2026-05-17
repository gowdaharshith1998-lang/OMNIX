"""Errors raised by omnix.semantic — structured, never silent.

Silent fallbacks to "Object" or sentinel types poison downstream gate logic.
Every error includes enough context to debug without re-running the subprocess.
"""

from __future__ import annotations


class JavaSemanticError(Exception):
    """Base error for the Java semantic layer."""


class UnresolvedSymbolError(JavaSemanticError):
    """JavaParser could not resolve a referenced symbol.

    Usually means a missing classpath entry. Includes symbol name + source location
    so the caller can either widen the classpath or accept the gap.
    """

    def __init__(self, symbol: str, file_path: str, line: int, message: str = "") -> None:
        self.symbol = symbol
        self.file_path = file_path
        self.line = line
        super().__init__(
            f"unresolved symbol {symbol!r} at {file_path}:{line}"
            + (f" — {message}" if message else "")
        )


class JavaSemanticTimeoutError(JavaSemanticError):
    """The JVM subprocess exceeded its wall-clock budget."""

    def __init__(self, file_path: str, timeout_s: float, stderr: str = "") -> None:
        self.file_path = file_path
        self.timeout_s = timeout_s
        self.stderr = stderr
        super().__init__(
            f"JavaParser subprocess timed out after {timeout_s}s on {file_path}"
            + (f"\nstderr: {stderr}" if stderr else "")
        )
