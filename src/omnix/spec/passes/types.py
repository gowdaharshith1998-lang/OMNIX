"""Pass 3: Types — classify return + parameter types as primitive vs reference,
and parse generic args per parameter.

Primitive set is the Java 21 set per JLS 4.2 (plus `void` for return-type
classification). Anything else — including boxed wrappers like
`java.lang.Integer` — counts as a reference type.

Generic arg parsing is shallow: a single `<...>` layer is split on commas at
depth 0. Nested generics (`Map<String, List<Integer>>`) are tolerated: the
inner `List<Integer>` is kept as a single arg, not split further. That's
sufficient for the v1 spec; deeper structural type info is M2 territory.
"""

from __future__ import annotations

from omnix.semantic import SemanticNode
from omnix.spec import TypeInfo

# JLS 4.2 primitive types + void (for return classification).
_JAVA_PRIMITIVES: frozenset[str] = frozenset(
    {
        "boolean",
        "byte",
        "short",
        "int",
        "long",
        "float",
        "double",
        "char",
        "void",
    }
)


def _is_primitive(type_fqn: str | None) -> bool:
    """True iff `type_fqn` is a Java primitive (or void)."""
    if type_fqn is None:
        return False
    return type_fqn in _JAVA_PRIMITIVES


def _strip_generics(type_fqn: str) -> str:
    """Return the erased type — everything before the first `<`."""
    idx = type_fqn.find("<")
    if idx == -1:
        return type_fqn
    return type_fqn[:idx]


def _parse_generic_args(type_fqn: str) -> tuple[str, ...]:
    """Split the top-level `<...>` argument list of `type_fqn`.

    Returns an empty tuple if no `<...>` is present. Splits only at depth 0
    commas so nested generics stay intact as single args.
    """
    open_idx = type_fqn.find("<")
    if open_idx == -1:
        return ()
    # Find the matching close `>` (we trust upstream balance).
    close_idx = type_fqn.rfind(">")
    if close_idx == -1 or close_idx <= open_idx + 1:
        return ()
    body = type_fqn[open_idx + 1 : close_idx]
    args: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in body:
        if ch == "<":
            depth += 1
            buf.append(ch)
        elif ch == ">":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            arg = "".join(buf).strip()
            if arg:
                args.append(arg)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        args.append(tail)
    return tuple(args)


def run(node: SemanticNode) -> TypeInfo:
    """Classify the node's return + param types and parse per-param generic args."""
    return_type = node.resolved_return_type
    is_return_primitive = _is_primitive(
        _strip_generics(return_type) if return_type is not None else None
    )

    params = tuple(node.resolved_param_types)
    are_params_primitive = tuple(_is_primitive(_strip_generics(p)) for p in params)
    generic_args = tuple(_parse_generic_args(p) for p in params)

    return TypeInfo(
        param_types=params,
        return_type=return_type,
        is_return_primitive=is_return_primitive,
        are_params_primitive=are_params_primitive,
        generic_args=generic_args,
    )
