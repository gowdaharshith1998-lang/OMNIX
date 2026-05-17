"""Errors raised by omnix.spec."""

from __future__ import annotations


class UnsupportedTargetLanguageError(Exception):
    """Raised when target_language is not supported in the current milestone.

    M1 supports only "java21". Multi-language support is M3+.
    """

    def __init__(self, target_language: str) -> None:
        self.target_language = target_language
        super().__init__(
            f"target_language={target_language!r} not supported in M1 — only 'java21' is valid"
        )
