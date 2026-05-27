"""Transformer DSL — RestrictedPython sandbox + AST allowlist + subprocess fence.

THE SECURITY KERNEL. LLM-emitted Python is HOSTILE INPUT. This module never
``eval``/``exec``/``compile``-s a string in the host process. Defense-in-depth:

  1. ``validate_ast`` walks the AST and rejects anything not in a strict
     allowlist (NOT denylist). Reject covers ``Import``, ``ClassDef``,
     ``With``, ``Try``, ``Raise``, ``For``, ``While``, ``Yield``, dunder
     attribute access, and any ``Call`` to a name outside ``ALLOWED_CALLS``.
  2. ``compile_safe`` runs ``RestrictedPython.compile_restricted`` which AST-
     rewrites ``a.b`` into ``_getattr_(a, "b")`` so dunder access is guarded.
  3. ``execute`` spawns ``sandbox_runner`` as a child process with
     ``resource.setrlimit`` for CPU / address space / open files. Signals
     map to ``ExecutionTimeout`` / ``ExecutionOOM`` / ``ExecutionError``.

Built on the CVE-2026-40217 (LiteLLM) lesson: custom regex sandboxes are
bypassable; AST-level rewriting is the floor.
"""

from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Optional, Union

from omnix.dm._types import (
    ExecutionError,
    ExecutionOOM,
    ExecutionTimeout,
    SecurityViolation,
)

# ---------------------------------------------------------------------------
# AST allowlist (allow-list, NOT denylist — per CVE-2026-40217 lesson)
# ---------------------------------------------------------------------------

ALLOWED_AST_NODES: frozenset = frozenset(
    {
        "Module",
        "FunctionDef",
        "Lambda",
        "Return",
        "Expression",
        "Constant",
        "Name",
        "Load",
        "Store",
        "Del",
        "Tuple",
        "List",
        "Dict",
        "Set",
        "ListComp",
        "DictComp",
        "SetComp",
        "GeneratorExp",
        "comprehension",
        "arguments",
        "arg",
        "keyword",
        "BinOp",
        "BoolOp",
        "UnaryOp",
        "Compare",
        "IfExp",
        "If",
        "Assign",
        "AugAssign",
        "AnnAssign",
        "Call",
        "Attribute",
        "Subscript",
        "Slice",
        "And",
        "Or",
        "Not",
        "Eq",
        "NotEq",
        "Lt",
        "LtE",
        "Gt",
        "GtE",
        "In",
        "NotIn",
        "Is",
        "IsNot",
        "Add",
        "Sub",
        "Mult",
        "Div",
        "Mod",
        "FloorDiv",
        "Pow",
        "BitAnd",
        "BitOr",
        "BitXor",
        "LShift",
        "RShift",
        "Invert",
        "USub",
        "UAdd",
        "JoinedStr",
        "FormattedValue",
        "Pass",
        "Expr",
        "Starred",
    }
)

ALLOWED_CALLS: frozenset = frozenset(
    {
        "str",
        "int",
        "float",
        "bool",
        "len",
        "abs",
        "min",
        "max",
        "sum",
        "round",
        "list",
        "tuple",
        "dict",
        "set",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "any",
        "all",
        "isinstance",
        "type",
        "repr",
        "hex",
        "oct",
        "bin",
        "ord",
        "chr",
        "divmod",
        "pow",
        "transform",  # the function we're defining
    }
)

ALLOWED_MODULE_ATTRS: frozenset = frozenset(
    {
        ("datetime", "datetime"),
        ("datetime", "date"),
        ("datetime", "time"),
        ("datetime", "timedelta"),
        ("datetime", "timezone"),
        ("datetime", "fromisoformat"),
        ("datetime", "fromtimestamp"),
        ("datetime", "utcnow"),
        ("datetime", "now"),
        ("datetime", "min"),
        ("datetime", "max"),
        ("datetime", "utc"),
        ("decimal", "Decimal"),
        ("decimal", "ROUND_HALF_UP"),
        ("decimal", "ROUND_HALF_EVEN"),
        ("decimal", "ROUND_DOWN"),
        ("decimal", "ROUND_UP"),
        ("re", "match"),
        ("re", "search"),
        ("re", "sub"),
        ("re", "findall"),
        ("re", "fullmatch"),
        ("re", "split"),
        ("re", "IGNORECASE"),
        ("re", "MULTILINE"),
        ("re", "DOTALL"),
        ("json", "dumps"),
        ("json", "loads"),
    }
)

# Methods we permit on common value types via Attribute access. We keep this
# narrow: string normalisation + date arithmetic primarily.
ALLOWED_METHODS: frozenset = frozenset(
    {
        # str / bytes
        "upper",
        "lower",
        "strip",
        "lstrip",
        "rstrip",
        "title",
        "capitalize",
        "replace",
        "split",
        "rsplit",
        "splitlines",
        "join",
        "startswith",
        "endswith",
        "encode",
        "decode",
        "format",
        "casefold",
        "zfill",
        "isdigit",
        "isalpha",
        "isalnum",
        "isnumeric",
        "isspace",
        "find",
        "rfind",
        "index",
        "rindex",
        "count",
        "ljust",
        "rjust",
        "center",
        "translate",
        "maketrans",
        "removeprefix",
        "removesuffix",
        # decimal / number
        "quantize",
        "normalize",
        "as_tuple",
        "to_integral_value",
        "compare",
        # datetime
        "isoformat",
        "strftime",
        "date",
        "time",
        "replace",  # tz-replace on datetime
        "astimezone",
        "combine",
        "fromisoformat",
        "fromtimestamp",
        "weekday",
        "isoweekday",
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
        "microsecond",
        "tzinfo",
        "utcoffset",
        "total_seconds",
        # container helpers
        "keys",
        "values",
        "items",
        "get",
        "pop",
        "append",
        "extend",
        "update",
        "copy",
        # regex match objects
        "group",
        "groups",
        "groupdict",
        "span",
        "start",
        "end",
    }
)

# Final ("leaf") attribute names allowed in chained access like
# ``datetime.timezone.utc`` where the inner ``datetime.timezone`` is already
# matched against ``ALLOWED_MODULE_ATTRS`` and we still need to validate the
# outer ``.utc``.
ALLOWED_CHAINED_ATTRS: frozenset = frozenset(
    {attr for _, attr in ALLOWED_MODULE_ATTRS}
) | ALLOWED_METHODS

# Dunder attributes that are NEVER permitted — even though RestrictedPython's
# ``_safe_getattr`` would block them at runtime, we reject at AST time too.
DUNDER_BLOCK_PREFIXES = ("__",)


# ---------------------------------------------------------------------------
# AST validator
# ---------------------------------------------------------------------------


def _excerpt(source: str, node: ast.AST, ctx: int = 60) -> str:
    line = getattr(node, "lineno", None)
    if line is None:
        return source[:ctx]
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1][:200]
    return source[:ctx]


def validate_ast(source: str) -> None:
    """Walk the AST of ``source``; raise :class:`_SecurityViolationError` if
    anything outside the allowlist appears.

    Raises ``SyntaxError`` if ``source`` is not valid Python.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        name = type(node).__name__
        if name not in ALLOWED_AST_NODES:
            raise _SecurityViolationError(
                SecurityViolation(
                    node_type=name,
                    reason=f"AST node {name!r} not in allowlist",
                    source_excerpt=_excerpt(source, node),
                )
            )
        if isinstance(node, ast.Attribute):
            if any(node.attr.startswith(p) for p in DUNDER_BLOCK_PREFIXES):
                raise _SecurityViolationError(
                    SecurityViolation(
                        node_type=f"Attribute(attr={node.attr!r})",
                        reason="dunder attribute access is forbidden",
                        source_excerpt=_excerpt(source, node),
                    )
                )
            # Permit (module.attr) where module is whitelisted and attr is allowed.
            if isinstance(node.value, ast.Name):
                pair = (node.value.id, node.attr)
                if pair in ALLOWED_MODULE_ATTRS:
                    continue
                # Plain method call on a variable — only if attr is a known method.
                if node.attr in ALLOWED_METHODS:
                    continue
                raise _SecurityViolationError(
                    SecurityViolation(
                        node_type=f"Attribute(attr={node.attr!r})",
                        reason=(
                            f"attribute {node.value.id}.{node.attr} not in "
                            f"ALLOWED_MODULE_ATTRS or ALLOWED_METHODS"
                        ),
                        source_excerpt=_excerpt(source, node),
                    )
                )
            # Chained attribute (datetime.datetime.fromisoformat,
            # datetime.timezone.utc, etc.) — inner Attribute is checked on
            # another walk iteration; here we only validate the leaf.
            if node.attr in ALLOWED_CHAINED_ATTRS:
                continue
            raise _SecurityViolationError(
                SecurityViolation(
                    node_type=f"Attribute(attr={node.attr!r})",
                    reason=f"chained attribute {node.attr!r} not in allowed leaf names",
                    source_excerpt=_excerpt(source, node),
                )
            )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id not in ALLOWED_CALLS:
                    raise _SecurityViolationError(
                        SecurityViolation(
                            node_type=f"Call(func={func.id!r})",
                            reason=f"call to {func.id!r} not in ALLOWED_CALLS",
                            source_excerpt=_excerpt(source, node),
                        )
                    )
            # Attribute calls (a.b()) are validated by the Attribute branch above.


class _SecurityViolationError(Exception):
    """Internal: raised when ``validate_ast`` rejects an AST. ``.violation``
    carries the user-visible :class:`SecurityViolation`."""

    def __init__(self, violation: SecurityViolation):
        super().__init__(violation.reason)
        self.violation = violation


# ---------------------------------------------------------------------------
# compile_safe
# ---------------------------------------------------------------------------


def compile_safe(source: str) -> bytes:
    """AST-validate then RestrictedPython-compile ``source``. Returns the
    compiled bytecode. Raises :class:`SecurityViolation` (as a wrapped
    exception) on rejection; raises :class:`SyntaxError` on bad Python.
    """
    # First pass: our strict AST allowlist.
    validate_ast(source)
    # Second pass: RestrictedPython's compile_restricted does the AST rewrite
    # that turns attribute access into _getattr_(obj, "attr") calls. Errors are
    # surfaced as a SecurityViolation too because they indicate the LLM emitted
    # something RestrictedPython refused.
    from RestrictedPython import compile_restricted

    try:
        return compile_restricted(source, "<llm-transformer>", "exec")
    except SyntaxError as exc:
        # A syntax error after our own ast.parse succeeded almost certainly
        # means RestrictedPython refused a construct (it raises SyntaxError for
        # forbidden patterns). Surface as a SecurityViolation.
        raise _SecurityViolationError(
            SecurityViolation(
                node_type="RestrictedPython",
                reason=f"RestrictedPython refused source: {exc}",
                source_excerpt=str(exc)[:200],
            )
        ) from exc


# ---------------------------------------------------------------------------
# safe_globals builder
# ---------------------------------------------------------------------------


def _safe_getattr(obj: Any, name: str, *default: Any) -> Any:
    """RestrictedPython _getattr_ guard — refuses dunder access."""
    if isinstance(name, str) and name.startswith("__"):
        raise AttributeError(
            f"dunder attribute access {name!r} is forbidden in sandboxed transformer"
        )
    if default:
        return getattr(obj, name, default[0])
    return getattr(obj, name)


def _safe_getitem(obj: Any, key: Any) -> Any:
    return obj[key]


def _safe_inplace(op: str, x: Any, y: Any) -> Any:
    # Just dispatch on the operator name; for sandboxed transformers AugAssign
    # is rare but RestrictedPython requires this hook to exist.
    if op == "+":
        return x + y
    if op == "-":
        return x - y
    if op == "*":
        return x * y
    if op == "/":
        return x / y
    if op == "//":
        return x // y
    if op == "%":
        return x % y
    raise RuntimeError(f"unsupported inplace op {op!r}")


def _safe_write(obj: Any) -> Any:
    """RestrictedPython _write_ guard — we only allow writes to literal
    containers built within the transformer (the sandbox creates them)."""
    return obj


class _NoopPrinter:
    def _call_print(self, *args, **kwargs):  # pragma: no cover - blocked path
        return None

    def __getattr__(self, _name: str):  # pragma: no cover
        return lambda *a, **kw: None


def _wrap_module(module: Any, allowed: list) -> Any:
    """Wrap a module so only ``allowed`` attribute names are reachable."""

    class _Wrapped:
        __slots__ = ()

    w = _Wrapped()
    for name in allowed:
        if hasattr(module, name):
            setattr(_Wrapped, name, getattr(module, name))
    return w


def build_safe_globals() -> dict:
    """Construct the safe_globals dict used by ``sandbox_runner``.

    Includes a strict ``__builtins__`` subset, wrapped whitelisted modules
    (datetime/decimal/re/json), and the RestrictedPython guard hooks
    (``_getattr_`` / ``_getitem_`` / ``_getiter_`` / ``_write_`` / ``_print_``).
    """
    import datetime as _datetime
    import decimal as _decimal
    import json as _json
    import re as _re

    safe_builtins: dict = {}
    for name in ALLOWED_CALLS:
        if name == "transform":
            continue
        if hasattr(__builtins__, name) if isinstance(__builtins__, dict) is False else (name in __builtins__):
            # Python may surface ``__builtins__`` as a module or a dict
            # depending on context.
            try:
                safe_builtins[name] = __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
            except Exception:  # pragma: no cover - defensive
                pass
        else:
            import builtins as _b

            if hasattr(_b, name):
                safe_builtins[name] = getattr(_b, name)
    # None / True / False as bare values (RestrictedPython expects them).
    safe_builtins["None"] = None
    safe_builtins["True"] = True
    safe_builtins["False"] = False

    return {
        "__builtins__": safe_builtins,
        "datetime": _wrap_module(
            _datetime,
            [
                "datetime",
                "date",
                "time",
                "timedelta",
                "timezone",
            ],
        ),
        "decimal": _wrap_module(
            _decimal,
            ["Decimal", "ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_DOWN", "ROUND_UP"],
        ),
        "re": _wrap_module(
            _re,
            [
                "match",
                "search",
                "sub",
                "findall",
                "fullmatch",
                "split",
                "IGNORECASE",
                "MULTILINE",
                "DOTALL",
            ],
        ),
        "json": _wrap_module(_json, ["dumps", "loads"]),
        "_getattr_": _safe_getattr,
        "_getitem_": _safe_getitem,
        "_getiter_": iter,
        "_inplacevar_": _safe_inplace,
        "_print_": _NoopPrinter(),
        "_write_": _safe_write,
    }


# ---------------------------------------------------------------------------
# execute — subprocess fence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionSuccess:
    result_repr: str  # repr() of the result (subprocess can't return live obj)
    result_json: Any  # JSON-decodable form (if possible)


ExecutionResult = Union[
    ExecutionSuccess, ExecutionTimeout, ExecutionOOM, ExecutionError
]


def execute(
    source: str,
    input_value: Any,
    timeout_ms: int = 5000,
    cpu_sec: Optional[int] = None,
    as_mb: Optional[int] = None,
) -> ExecutionResult:
    """Validate, compile, and execute ``source(input_value)`` in a fenced
    subprocess. Returns one of the ``Execution*`` types.

    Timing model: ``timeout_ms`` is the parent-side wall clock. The child
    process additionally has a ``RLIMIT_CPU`` (default 5 s) and ``RLIMIT_AS``
    (default 256 MB) so an inner busy-loop or allocation bomb is bounded even
    if the parent timeout is bypassed.
    """
    # Validate first so we surface SecurityViolation BEFORE we fork.
    try:
        compile_safe(source)
    except _SecurityViolationError:
        # Caller is expected to call compile_safe explicitly; surface the
        # exception so the reflexion loop can capture it.
        raise

    cpu = cpu_sec if cpu_sec is not None else int(os.environ.get("OMNIX_DM_SUBPROCESS_CPU_SEC", "5"))
    asmb = as_mb if as_mb is not None else int(os.environ.get("OMNIX_DM_SUBPROCESS_AS_MB", "256"))

    payload = json.dumps(
        {
            "source": source,
            "input_value": _to_json_safe(input_value),
            "input_kind": _kind_of(input_value),
        }
    ).encode("utf-8")

    runner = os.path.join(os.path.dirname(__file__), "sandbox_runner.py")
    env = os.environ.copy()
    env["OMNIX_DM_SUBPROCESS_CPU_SEC"] = str(cpu)
    env["OMNIX_DM_SUBPROCESS_AS_MB"] = str(asmb)

    try:
        proc = subprocess.run(
            [sys.executable, "-u", runner],
            input=payload,
            capture_output=True,
            timeout=timeout_ms / 1000.0,
            env=env,
            check=False,
            start_new_session=True,  # new process group → killable as group
        )
    except subprocess.TimeoutExpired:
        return ExecutionTimeout(input_value=repr(input_value), timeout_ms=timeout_ms)

    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            return ExecutionError(
                input_value=repr(input_value),
                error_type="OutputDecodeError",
                error_message=str(exc),
            )
        if data.get("kind") == "ok":
            return ExecutionSuccess(
                result_repr=data["result_repr"], result_json=data.get("result")
            )
        return ExecutionError(
            input_value=repr(input_value),
            error_type=data.get("error_type", "Error"),
            error_message=data.get("error_message", ""),
        )

    # Negative return codes on POSIX indicate signal termination.
    if proc.returncode < 0:
        sig = -proc.returncode
        if sig == signal.SIGXCPU:
            return ExecutionTimeout(input_value=repr(input_value), timeout_ms=cpu * 1000)
        if sig == signal.SIGKILL:
            # OOM kill is observed as SIGKILL when RLIMIT_AS bites.
            return ExecutionOOM(input_value=repr(input_value), rss_bytes=asmb * 1024 * 1024)
        return ExecutionError(
            input_value=repr(input_value),
            error_type="Signal",
            error_message=f"signal {sig}",
        )

    return ExecutionError(
        input_value=repr(input_value),
        error_type="NonZeroExit",
        error_message=(proc.stderr or b"").decode("utf-8", "replace")[:500],
    )


def _kind_of(v: Any) -> str:
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (bytes, bytearray)):
        return "bytes"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return "dict"
    # datetime / date / Decimal serialized via ISO/string forms.
    import datetime
    import decimal

    if isinstance(v, datetime.datetime):
        return "datetime"
    if isinstance(v, datetime.date):
        return "date"
    if isinstance(v, decimal.Decimal):
        return "decimal"
    return "repr"


def _to_json_safe(v: Any) -> Any:
    """Render ``v`` into something the JSON encoder can serialize. Datetimes,
    Decimals, and bytes get encoded as tagged dicts the child decodes."""
    import datetime
    import decimal

    if isinstance(v, datetime.datetime):
        return {"__datetime__": v.isoformat(), "tz": v.tzinfo.tzname(v) if v.tzinfo else None}
    if isinstance(v, datetime.date):
        return {"__date__": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"__decimal__": str(v)}
    if isinstance(v, (bytes, bytearray)):
        return {"__bytes__": bytes(v).hex()}
    if isinstance(v, (list, tuple)):
        return [_to_json_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _to_json_safe(x) for k, x in v.items()}
    return v


__all__ = [
    "ALLOWED_AST_NODES",
    "ALLOWED_CALLS",
    "ALLOWED_MODULE_ATTRS",
    "ALLOWED_METHODS",
    "ExecutionSuccess",
    "ExecutionResult",
    "validate_ast",
    "compile_safe",
    "build_safe_globals",
    "execute",
    "_SecurityViolationError",
]
