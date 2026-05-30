"""Retry-on-gate-failure wrapper around the orchestrator dispatch loop.

Phase 7 — re-dispatches failed nodes up to N=3 times with structured gate-failure
context appended to the prompt.

Co-existence with Phase 5
-------------------------
`omnix.orchestrator.dispatcher` is being written by a parallel agent. To avoid
a write race, this module exposes `run_with_retry` as a SIBLING top-level entry
point rather than mutating `dispatcher.run`. Callers choose:

  - `dispatcher.run(...)`       — no retry, no gates (Phase 5)
  - `retry.run_with_retry(...)` — retry + gates (Phase 7)

That way both phases land cleanly without either touching the other's file.

Contract for dispatch_fn and gate_runner
----------------------------------------
Both are injectable callables so this module is unit-testable without a live
LLM or a JVM. Production defaults lazy-import the real implementations.

  - `dispatch_fn(prompt: str) -> str`
  - `gate_runner(spec, response_text, target_language) -> GateResult`

Retry semantics
---------------
- Gate FAILURES (GateResult.passed is False) trigger a retry with context appended.
- `dispatch_fn` exceptions (rate limit, network) PROPAGATE — those are the LLM
  client's responsibility to retry, not this layer's.
- `GateCrashError` from `gate_runner` PROPAGATES — a crash inside a gate impl is
  a bug, not a gate-failure result.
- Each node retries independently. A node that exhausts retries does NOT stop
  other nodes from running (R-7.3).
- `PROMPT_TEMPLATE_VERSION` is constant across retries — only the appended
  context changes (R-7.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from omnix.gates.result import GateResult
from omnix.orchestrator.attempt import RebuildAttempt, sha256_hex
from omnix.orchestrator.human_review import HumanReviewRecord, RetryRunReport
from omnix.orchestrator.prompt_template import PROMPT_TEMPLATE_VERSION
from omnix.spec import Spec

MAX_RETRIES_DEFAULT = 3
RESPONSE_EXCERPT_CHARS = 200


class RetryExhaustedError(Exception):
    """Internal signal — a node hit max_retries with no success.

    Caught by `run_with_retry` and surfaced via `HumanReviewRecord`. Callers
    never see this exception; it's a control-flow primitive inside this module.
    """


# ---------- prompt construction ---------------------------------------------

def _build_base_prompt(spec: Spec, target_language: str) -> str:
    """Deterministic prompt for the first attempt at a node.

    Same spec + same target_language → byte-identical prompt. That property is
    relied on by spec_hash + prompt_text_hash in RebuildAttempt.
    """
    return (
        f"# OMNIX rebuild prompt (template v{PROMPT_TEMPLATE_VERSION})\n"
        f"## Target language\n{target_language}\n\n"
        f"## SPEC\n{spec.to_json(indent=2)}\n\n"
        f"## Instruction\n"
        f"Produce a {target_language} implementation matching the SPEC above. "
        f"Return only source code.\n"
    )


def format_retry_context(prior_attempt: RebuildAttempt, prior_result: GateResult) -> str:
    """Build the retry context block to append to the next prompt (R-7.4).

    Format:

        ## Previous attempt failed

        Previous response (first 200 chars):
        <excerpt>

        ### Gate <N> failure: <gate-name>
        Message: <message>
        Details:
          <key>: <value>
          ...

        ### Gate <M> failure: <gate-name>
        ...

        Please address each failure and produce a corrected version.

    Deterministic: same prior_attempt + prior_result → byte-identical output.
    Error key/value pairs are sorted to stabilize across dict insertion order.

    Degenerate case: if `prior_result.errors` is empty (shouldn't happen — gates
    that fail must attach an error), we still emit the header + footer so the
    next prompt is well-formed. Documenting this so reviewers know it's a guard,
    not a feature.
    """
    excerpt = prior_attempt.response_text[:RESPONSE_EXCERPT_CHARS]
    parts: list[str] = [
        "## Previous attempt failed",
        "",
        f"Previous response (first {RESPONSE_EXCERPT_CHARS} chars):",
        excerpt,
        "",
    ]
    for err in prior_result.errors:
        parts.append(f"### Gate {err.gate_number} failure: {err.gate_name}")
        parts.append(f"Message: {err.message}")
        if err.details:
            parts.append("Details:")
            for key in sorted(err.details.keys()):
                parts.append(f"  {key}: {err.details[key]}")
        parts.append("")
    parts.append("Please address each failure and produce a corrected version.")
    return "\n".join(parts)


def _build_retry_prompt(
    spec: Spec,
    target_language: str,
    prior_attempt: RebuildAttempt,
    prior_result: GateResult,
) -> str:
    """Base prompt + retry context block. Same template version, more context."""
    base = _build_base_prompt(spec, target_language)
    context = format_retry_context(prior_attempt, prior_result)
    return f"{base}\n{context}\n"


# ---------- default lazy adapters -------------------------------------------

def _default_dispatch(prompt: str) -> str:
    """Lazy adapter to `omnix.fabric.dispatcher.dispatch`.

    Kept thin so tests don't have to monkey with import paths. Production callers
    that already have a configured fabric pipeline should pass their own
    `dispatch_fn` rather than rely on this.
    """
    from omnix.fabric.dispatcher import dispatch  # local import — avoid cycle

    payload: dict[str, Any] = {
        "task_kind": "rebuild",
        "messages": [{"role": "user", "content": prompt}],
    }
    result = dispatch(payload)
    # fabric.dispatch returns a dict with "text" / "content" — pick whichever exists.
    if isinstance(result, dict):
        for key in ("text", "content", "response"):
            if key in result and isinstance(result[key], str):
                return result[key]
    raise RuntimeError("default dispatch adapter could not extract response text")


def _default_gate_runner(spec: Spec, response_text: str, target_language: str) -> GateResult:
    """Adapter from the orchestrator gate-runner contract to ``gates.runner.run``.

    The orchestrator gate-runner Callable is ``(spec, response_text,
    target_language) -> GateResult``; ``gates.runner.run`` is
    ``(rebuild_attempt, spec, source_code=None)``. We pass the candidate code as
    ``source_code`` so the gates check exactly ``response_text`` against ``spec``,
    and a RebuildAttempt carrying the context this adapter actually has
    (node_fqn, spec_hash, response_text, prompt template version). ``run`` reads
    the attempt only as a *fallback* for the code — which ``source_code``
    overrides — and never embeds it in the returned GateResult, so no provenance
    is fabricated into any receipt.
    """
    del target_language  # gates infer language from the code/spec; unused here
    from datetime import datetime, timezone

    from omnix.gates.runner import run as _run  # local import — avoid cycle

    attempt = RebuildAttempt(
        node_fqn=spec.identity.fqn,
        spec_hash=sha256_hex(spec.to_json()),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_text_hash="",
        response_text=response_text,
        timestamp=datetime.now(timezone.utc),
        model="",
    )
    return _run(attempt, spec, source_code=response_text)


def _default_nodes_for(project_path: Path) -> Sequence[Spec]:
    """Resolve rebuild nodes when the caller did not inject ``nodes``.

    Automatic project-walk discovery (parse -> semantic -> ``Spec`` in
    dependency-topological order) is not implemented in this milestone — there
    is no ``project_path -> Spec`` builder yet. Rather than fail with an opaque
    ``ImportError`` on a helper that never existed, surface the gap honestly so
    callers know to pass ``nodes=`` explicitly (as every current caller and
    test already does).
    """
    raise NotImplementedError(
        f"run_with_retry could not auto-discover rebuild nodes for {project_path!r}: "
        "automatic project-walk node discovery is not implemented yet. "
        "Pass nodes=<sequence of Spec> explicitly."
    )


# ---------- main entry point -------------------------------------------------

def run_with_retry(
    project_path: Path,
    *,
    target_language: str = "java21",
    max_retries: int = MAX_RETRIES_DEFAULT,
    dispatch_fn: Callable[[str], str] | None = None,
    gate_runner: Callable[..., GateResult] | None = None,
    model: str = "claude-opus-4.7",
    nodes: Iterable[Spec] | None = None,
) -> RetryRunReport:
    """Walk the project nodes and rebuild each with retry-on-gate-failure.

    For each node:
      1. Dispatch (attempt 1).
      2. Run gates.
      3. If passed: record success, move on.
      4. If failed: format retry context, append to next prompt, dispatch again.
      5. Repeat up to `max_retries`.
      6. On exhaustion: emit a HumanReviewRecord with the full attempt + gate
         history, then continue with the next node (R-7.3).

    `dispatch_fn` and `gate_runner` are injectable. Production defaults lazy-
    import `omnix.fabric.dispatcher.dispatch` and `omnix.gates.runner.run`.

    `nodes` is injectable and currently required in practice: automatic
    project-walk discovery is not implemented, so `nodes=None` raises
    `NotImplementedError` (see `_default_nodes_for`).
    """
    if max_retries < 1:
        raise ValueError(f"max_retries must be >= 1, got {max_retries}")

    _dispatch = dispatch_fn if dispatch_fn is not None else _default_dispatch
    _gates = gate_runner if gate_runner is not None else _default_gate_runner
    _nodes: Sequence[Spec] = (
        tuple(nodes) if nodes is not None else _default_nodes_for(project_path)
    )

    successful: list[RebuildAttempt] = []
    review: list[HumanReviewRecord] = []
    history: list[RebuildAttempt] = []

    for spec in _nodes:
        node_attempts: list[RebuildAttempt] = []
        node_results: list[GateResult] = []
        spec_hash = sha256_hex(spec.to_json())

        prior_attempt: RebuildAttempt | None = None
        prior_result: GateResult | None = None

        for attempt_idx in range(1, max_retries + 1):
            if prior_attempt is None or prior_result is None:
                prompt = _build_base_prompt(spec, target_language)
            else:
                prompt = _build_retry_prompt(spec, target_language, prior_attempt, prior_result)

            # dispatch_fn exceptions propagate unchanged (per DON'Ts).
            response = _dispatch(prompt)

            attempt = RebuildAttempt(
                node_fqn=spec.identity.fqn,
                spec_hash=spec_hash,
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
                prompt_text_hash=sha256_hex(prompt),
                response_text=response,
                timestamp=RebuildAttempt.now_utc(),
                model=model,
                attempt_number=attempt_idx,
            )
            node_attempts.append(attempt)
            history.append(attempt)

            # GateCrashError propagates unchanged — gate-impl bug, not a gate failure.
            result = _gates(spec=spec, response_text=response, target_language=target_language)
            node_results.append(result)

            if result.passed:
                successful.append(attempt)
                break

            prior_attempt = attempt
            prior_result = result
        else:
            # Loop exhausted with no `break` — node never passed.
            review.append(
                HumanReviewRecord(
                    node_fqn=spec.identity.fqn,
                    attempts=tuple(node_attempts),
                    gate_results=tuple(node_results),
                    final_gate_errors=node_results[-1].errors if node_results else (),
                    reason="max_retries_exhausted",
                )
            )

    return RetryRunReport(
        successful_attempts=tuple(successful),
        flagged_for_human_review=tuple(review),
        full_attempt_history=tuple(history),
    )
