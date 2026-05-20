"""Gate 6 Reflexion retry helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ReflexionContext:
    original_prompt: str
    failed_replica: str
    gate6_failures: list[dict]


@dataclass(frozen=True)
class RetryOutcome:
    succeeded: bool
    source: str | None
    attempts: int
    last_error: str | None


def refine_prompt(ctx: ReflexionContext) -> str:
    parts = [
        f"Original task: {ctx.original_prompt}",
        "",
        f"Your prior replica was rejected by behavioral Gate 6 on {len(ctx.gate6_failures)} fixture(s).",
        "",
        "Specific byte-level diffs:",
    ]
    for failure in ctx.gate6_failures:
        legacy = str(failure.get("legacy_stdout", ""))
        candidate = str(failure.get("candidate_stdout", ""))
        parts.extend(
            [
                f"  Fixture {failure.get('fixture_id', '<unknown>')}:",
                f"    Legacy stdout (hex):    {legacy.encode('utf-8', errors='replace').hex()[:200]}",
                f"    Candidate stdout (hex): {candidate.encode('utf-8', errors='replace').hex()[:200]}",
                f"    First differing byte at offset: {_first_diff_offset(legacy, candidate)}",
                f"    Likely root cause hint: {_root_cause_hint(legacy, candidate)}",
            ]
        )
    parts.extend(
        [
            "",
            "Common root causes:",
            "- Decimal vs float for COMP-3 fields",
            "- Spacing/padding in edited PIC clauses",
            "- Trailing newline mismatch",
            "- Sign nibble handling in packed-decimal",
            "- PIC X(n) right-pad with spaces",
            "",
            "Generate a corrected replica preserving all original constraints.",
            "Return ONLY Python source code, no markdown fences.",
        ]
    )
    return "\n".join(parts)


def retry_gate6_failed(
    *,
    original_prompt: str,
    original_replica: str,
    gate_failures: list[dict],
    attempts_remaining: int,
    llm_dispatch: Callable[[str], str],
    validator: Callable[[str], None] | None = None,
) -> RetryOutcome:
    attempts = 0
    last_error: str | None = None
    prompt = refine_prompt(
        ReflexionContext(
            original_prompt=original_prompt,
            failed_replica=original_replica,
            gate6_failures=gate_failures,
        )
    )
    for _ in range(max(0, attempts_remaining)):
        attempts += 1
        source = llm_dispatch(prompt)
        try:
            if validator is not None:
                validator(source)
            return RetryOutcome(True, source, attempts, None)
        except Exception as exc:
            last_error = str(exc)
            prompt = refine_prompt(
                ReflexionContext(
                    original_prompt=prompt,
                    failed_replica=source,
                    gate6_failures=gate_failures,
                )
            )
    return RetryOutcome(False, None, attempts, last_error)


def _first_diff_offset(a: str, b: str) -> int:
    ab = a.encode("utf-8", errors="replace")
    bb = b.encode("utf-8", errors="replace")
    for idx, (left, right) in enumerate(zip(ab, bb)):
        if left != right:
            return idx
    return min(len(ab), len(bb))


def _root_cause_hint(legacy: str, candidate: str) -> str:
    if legacy.rstrip("\n") == candidate.rstrip("\n") and legacy != candidate:
        return "trailing newline / record terminator"
    if legacy.replace(" ", "") == candidate.replace(" ", "") and legacy != candidate:
        return "spacing/padding"
    if legacy.replace(".", "") == candidate.replace(".", "") and legacy != candidate:
        return "PIC V scale handling"
    if legacy.lstrip("0") == candidate.lstrip("0") and legacy != candidate:
        return "zero-fill in numeric PIC"
    return "see byte diff above"

