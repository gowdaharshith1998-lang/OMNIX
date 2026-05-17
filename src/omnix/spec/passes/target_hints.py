"""Pass 5: Target hints — language-specific idiom guidance for the LLM.

These are static per language. The generator does NOT compose hints; it only
selects the right list. Keeping them here (not in the generator) makes it
trivial to bolt on additional languages in M3+ without touching the
orchestration code.
"""

from __future__ import annotations

from omnix.spec import UnsupportedTargetLanguageError

JAVA21_HINTS: tuple[str, ...] = (
    "Use `var` for local variable type inference where the type is obvious from the right-hand side",
    "Prefer records for simple data classes (no getters/setters/equals/hashCode boilerplate)",
    "Use switch expressions over switch statements where the result is consumed",
    "Diamond operator `<>` for generic instantiation",
    "try-with-resources for any AutoCloseable",
    'Text blocks ("""...""") for multi-line strings',
    "Optional<T> for nullable return types where contextually appropriate",
    "Avoid raw types; always parameterize generics",
)


def run(target_language: str) -> tuple[str, ...]:
    """Return the idiom hints for `target_language`.

    Raises UnsupportedTargetLanguageError for anything other than `java21`.
    """
    if target_language == "java21":
        return JAVA21_HINTS
    raise UnsupportedTargetLanguageError(target_language)
