"""Operator decision queue abstractions for COBOL modernization."""

from __future__ import annotations

import select
import sys
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

from omnix.orchestrator.cobol.errors import DecisionUnavailable
from omnix.orchestrator.cobol.run_state import RunState


@dataclass(frozen=True)
class DecisionOption:
    key: str
    label: str
    detail: str
    cost_estimate_usd: float | None = None
    recommended: bool = False


@dataclass(frozen=True)
class DecisionRequest:
    decision_id: str
    kind: str
    context: dict[str, object]
    options: tuple[DecisionOption, ...]
    default_key: str


class DecisionQueue(Protocol):
    def ask(self, request: DecisionRequest, *, timeout_s: float | None) -> str: ...

    def list_pending(self) -> list[DecisionRequest]: ...

    def answer(self, decision_id: str, key: str) -> None: ...


class TerminalDecisionQueue:
    def __init__(
        self,
        run_state: RunState,
        *,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._state = run_state
        self._input = input_fn
        self._output = output_fn or (lambda msg: print(msg, file=sys.stderr))

    def ask(self, request: DecisionRequest, *, timeout_s: float | None) -> str:
        existing = self._state.get_decision(request.decision_id)
        if existing.get("answer"):
            return str(existing["answer"])
        self._state.put_decision_request(request.decision_id, request.kind, _request_payload(request))
        valid = {option.key for option in request.options}
        prompt = _format_prompt(request, timeout_s)
        answer = self._read_answer(prompt, timeout_s).strip().lower() or request.default_key
        if answer not in valid:
            answer = request.default_key
        self._state.answer_decision(request.decision_id, answer)
        return answer

    def list_pending(self) -> list[DecisionRequest]:
        return [_request_from_payload(row["payload_json"]) for row in self._state.pending_decisions()]

    def answer(self, decision_id: str, key: str) -> None:
        self._state.put_decision_request(
            decision_id,
            "external",
            {
                "decision_id": decision_id,
                "kind": "external",
                "context": {},
                "options": [],
                "default_key": key,
            },
        )
        self._state.answer_decision(decision_id, key)

    def _read_answer(self, prompt: str, timeout_s: float | None) -> str:
        if self._input is not None:
            return self._input(prompt)
        self._output(prompt)
        if timeout_s is not None and timeout_s <= 0:
            return ""
        if timeout_s is not None:
            readable, _, _ = select.select([sys.stdin], [], [], timeout_s)
            if not readable:
                return ""
        return sys.stdin.readline()


class PersistentDecisionQueue:
    def __init__(self, run_state: RunState) -> None:
        self._state = run_state

    def ask(self, request: DecisionRequest, *, timeout_s: float | None) -> str:
        _ = timeout_s
        self._state.put_decision_request(request.decision_id, request.kind, _request_payload(request))
        raise DecisionUnavailable(
            f"decision {request.decision_id} is queued; answer it with `omnix cobol decide`"
        )

    def list_pending(self) -> list[DecisionRequest]:
        return [_request_from_payload(row["payload_json"]) for row in self._state.pending_decisions()]

    def answer(self, decision_id: str, key: str) -> None:
        self._state.answer_decision(decision_id, key)


def _request_payload(request: DecisionRequest) -> dict[str, object]:
    return {
        "decision_id": request.decision_id,
        "kind": request.kind,
        "context": request.context,
        "options": [asdict(option) for option in request.options],
        "default_key": request.default_key,
    }


def _request_from_payload(payload_json: str) -> DecisionRequest:
    import json

    payload = json.loads(payload_json)
    return DecisionRequest(
        decision_id=str(payload["decision_id"]),
        kind=str(payload["kind"]),
        context=dict(payload.get("context") or {}),
        options=tuple(DecisionOption(**option) for option in payload.get("options") or []),
        default_key=str(payload["default_key"]),
    )


def _format_prompt(request: DecisionRequest, timeout_s: float | None) -> str:
    lines = [f"DECISION (kind: {request.kind})"]
    program = request.context.get("program_id")
    if program:
        lines.append(f"  Program {program}: {request.context}")
    for option in request.options:
        suffix = " [default]" if option.key == request.default_key else ""
        rec = " (recommended)" if option.recommended else ""
        cost = f" (${option.cost_estimate_usd:.2f} est)" if option.cost_estimate_usd is not None else ""
        lines.append(f"  [{option.key}] {option.label}{cost}{rec}: {option.detail}{suffix}")
    if timeout_s is None:
        lines.append(f"Choose [{'/'.join(o.key for o in request.options)}]: ")
    else:
        lines.append(
            f"Choose [{'/'.join(o.key for o in request.options)}] "
            f"(default {request.default_key} after {timeout_s:g}s): "
        )
    return "\n".join(lines)

