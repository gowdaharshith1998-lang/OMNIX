"""Tree-sitter extraction for Python sources."""

from __future__ import annotations

import os
from collections import defaultdict

from tree_sitter import Language, Node, Parser
import tree_sitter_python as tsp

from src.graph.store import GraphStore
from src.parser import should_skip_dir
from src.parser.tree_parse_cache import get_shared_parser, parse_tree_cached

_PY = Language(tsp.language())


def _py_parser() -> Parser:
    return get_shared_parser("python", _PY)


def _text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _lines_for_node(source: bytes, node: Node) -> int:
    return node.end_point[0] - node.start_point[0] + 1


def parse_python_files(root: str, store: GraphStore) -> int:
    root = os.path.abspath(root)
    count = 0
    files: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "rb") as f:
                    src = f.read()
            except OSError:
                continue
            files.append((rel, src.decode("utf-8", errors="replace")))
            count += 1

    for rel, text in files:
        _pass1_definitions(store, rel, text)
    index = _build_call_index(store)
    for rel, text in files:
        _pass2_calls(store, rel, text, index)
    store.commit()
    return count


def _build_call_index(store: GraphStore) -> dict[str, list[tuple[str, str]]]:
    """Map short function name -> [(node_id, file_path), ...]."""
    by_short: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for n in store.iter_all_nodes():
        if n.type not in ("function", "method"):
            continue
        short = n.name.split(".")[-1]
        fp = n.file_path or ""
        by_short[short].append((n.id, fp))
    return by_short


def _pass1_definitions(store: GraphStore, rel: str, text: str) -> None:
    source = text.encode("utf-8")
    p = _py_parser()
    tree = parse_tree_cached("python", rel, p, source)
    file_id = rel
    lc = text.count("\n") + 1 if text else 1
    store.add_node(
        id=file_id,
        name=os.path.basename(rel),
        type="file",
        file_path=rel,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={"language": "python"},
    )
    ctx = _DefContext(store=store, file_id=file_id, rel=rel, source=source)
    for ch in tree.root_node.children:
        if ch.type in ("import_statement", "import_from_statement"):
            _import_edges(ctx, ch)
        elif ch.type == "decorated_definition":
            _walk_decorated_definition(ctx, ch)
        elif ch.type == "function_definition":
            _define_function(ctx, ch, class_stack=[])
        elif ch.type == "class_definition":
            _define_class(ctx, ch, class_stack=[])


def _pass2_calls(
    store: GraphStore,
    rel: str,
    text: str,
    index: dict[str, list[tuple[str, str]]],
) -> None:
    source = text.encode("utf-8")
    p = _py_parser()
    tree = parse_tree_cached("python", rel, p, source)
    ctx = _CallContext(store=store, rel=rel, source=source, index=index)
    _walk_calls_module(ctx, tree.root_node)


class _CallContext:
    __slots__ = ("store", "rel", "source", "index", "stack")

    def __init__(
        self,
        store: GraphStore,
        rel: str,
        source: bytes,
        index: dict[str, list[tuple[str, str]]],
        stack: list[str] | None = None,
    ) -> None:
        self.store = store
        self.rel = rel
        self.source = source
        self.index = index
        self.stack = stack if stack is not None else []


def _walk_calls_module(ctx: _CallContext, node: Node) -> None:
    for ch in node.children:
        if ch.type == "decorated_definition":
            _walk_calls_decorated(ctx, ch)
        elif ch.type == "function_definition":
            _walk_calls_function(ctx, ch, class_prefix=None)
        elif ch.type == "class_definition":
            _walk_calls_class(ctx, ch)


def _walk_calls_decorated(ctx: _CallContext, node: Node) -> None:
    subject: Node | None = None
    for c in node.children:
        if c.type in ("function_definition", "class_definition"):
            subject = c
            break
    if subject is None:
        return
    if subject.type == "class_definition":
        _walk_calls_class(ctx, subject)
    else:
        _walk_calls_function(ctx, subject, class_prefix=None)


def _walk_calls_class(ctx: _CallContext, node: Node) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    cname = _text(ctx.source, name_node)
    body = node.child_by_field_name("body")
    if not body:
        return
    for ch in body.children:
        if ch.type == "decorated_definition":
            subj: Node | None = None
            for c in ch.children:
                if c.type in ("function_definition", "class_definition"):
                    subj = c
                    break
            if subj and subj.type == "function_definition":
                _walk_calls_function(ctx, subj, class_prefix=cname)
            elif subj and subj.type == "class_definition":
                _walk_calls_class(ctx, subj)
        elif ch.type == "function_definition":
            _walk_calls_function(ctx, ch, class_prefix=cname)
        elif ch.type == "class_definition":
            _walk_calls_class(ctx, ch)


def _walk_calls_function(ctx: _CallContext, node: Node, class_prefix: str | None) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    fname = _text(ctx.source, name_node)
    if class_prefix is not None:
        fid = f"{ctx.rel}::{class_prefix}.{fname}"
        qual_stack = [class_prefix, fname]
    else:
        fid = f"{ctx.rel}::{fname}"
        qual_stack = [fname]

    ctx.stack.append(fid)
    body = node.child_by_field_name("body")
    if body:
        _scan_calls_in_block(ctx, body)
        for ch in body.children:
            if ch.type == "function_definition":
                _walk_nested_calls(ctx, ch, qual_stack)

    ctx.stack.pop()


def _walk_nested_calls(ctx: _CallContext, node: Node, parent_qual: list[str]) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    fname = _text(ctx.source, name_node)
    qual = parent_qual + [fname]
    fid = f"{ctx.rel}::{'.'.join(qual)}"
    ctx.stack.append(fid)
    body = node.child_by_field_name("body")
    if body:
        _scan_calls_in_block(ctx, body)
        for ch in body.children:
            if ch.type == "function_definition":
                _walk_nested_calls(ctx, ch, qual)
    ctx.stack.pop()


def _scan_calls_in_block(ctx: _CallContext, node: Node) -> None:
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "call":
            _emit_call_edge(ctx, n)
        stack.extend(reversed(n.children))


def _emit_call_edge(ctx: _CallContext, call_node: Node) -> None:
    if not ctx.stack:
        return
    caller = ctx.stack[-1]
    callee_name = _call_callee_short_name(ctx.source, call_node)
    if not callee_name or callee_name in ("print", "super", "len", "range", "str", "int", "dict", "list", "set"):
        return
    target = _resolve_callee(ctx.rel, callee_name, ctx.index)
    if target and target != caller:
        ctx.store.add_edge(caller, target, "CALLS")


def _call_callee_short_name(source: bytes, call_node: Node) -> str | None:
    fn = call_node.child_by_field_name("function")
    if fn is None:
        for c in call_node.children:
            if c.type in ("identifier", "attribute"):
                fn = c
                break
    if fn is None:
        return None
    if fn.type == "identifier":
        return _text(source, fn)
    if fn.type == "attribute":
        attr = fn.child_by_field_name("attribute")
        obj = fn.child_by_field_name("object")
        if obj and obj.type == "identifier" and _text(source, obj) == "self" and attr:
            return _text(source, attr)
        return None
    return None


def _resolve_callee(caller_file: str, short: str, index: dict[str, list[tuple[str, str]]]) -> str | None:
    cands = index.get(short)
    if not cands:
        return None
    same = [nid for nid, fp in cands if fp == caller_file]
    if same:
        return same[0]
    return cands[0][0]


def _walk_decorated_definition(ctx: _DefContext, node: Node) -> None:
    decs: list[str] = []
    subject: Node | None = None
    for c in node.children:
        if c.type == "decorator":
            decs.append(_decorator_name(ctx.source, c))
        elif c.type in ("function_definition", "class_definition"):
            subject = c
            break
    if subject is None:
        return
    if subject.type == "class_definition":
        _define_class(ctx, subject, class_stack=[], pending_decorators=decs)
    else:
        _define_function(ctx, subject, class_stack=[], pending_decorators=decs)


def _decorator_name(source: bytes, dec_node: Node) -> str:
    for c in dec_node.children:
        if c.type == "identifier":
            return _text(source, c)
        if c.type == "call":
            return _call_target_name(source, c)
    return "decorator"


def _call_target_name(source: bytes, call_node: Node) -> str:
    fn = call_node.child_by_field_name("function")
    if fn is None:
        for c in call_node.children:
            if c.type in ("identifier", "attribute"):
                fn = c
                break
    if fn is None:
        return "call"
    if fn.type == "identifier":
        return _text(source, fn)
    if fn.type == "attribute":
        return _attribute_path(source, fn)
    return _text(source, fn)


def _attribute_path(source: bytes, attr_node: Node) -> str:
    parts: list[str] = []
    cur: Node | None = attr_node
    while cur is not None:
        if cur.type == "attribute":
            obj = cur.child_by_field_name("object")
            attr = cur.child_by_field_name("attribute")
            if attr:
                parts.append(_text(source, attr))
            cur = obj
        elif cur.type == "identifier":
            parts.append(_text(source, cur))
            cur = None
        else:
            break
    return ".".join(reversed(parts))


class _DefContext:
    __slots__ = ("store", "file_id", "rel", "source")

    def __init__(self, store: GraphStore, file_id: str, rel: str, source: bytes) -> None:
        self.store = store
        self.file_id = file_id
        self.rel = rel
        self.source = source


def _define_class(
    ctx: _DefContext,
    node: Node,
    class_stack: list[str],
    pending_decorators: list[str] | None = None,
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    class_name = _text(ctx.source, name_node)
    cid = f"{ctx.rel}::{class_name}"
    body = node.child_by_field_name("body")
    supers = node.child_by_field_name("superclasses")
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    store = ctx.store
    store.add_node(
        id=cid,
        name=class_name,
        type="class",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata={"bases": _class_bases(ctx.source, supers)},
    )
    store.add_edge(ctx.file_id, cid, "DEFINES")
    if pending_decorators:
        for d in pending_decorators:
            did = _decorator_node_id(ctx.rel, d)
            _ensure_decorator_node(store, did, d, ctx.rel)
            store.add_edge(did, cid, "DECORATES")

    new_stack = class_stack + [class_name]
    if body:
        for ch in body.children:
            if ch.type == "decorated_definition":
                _walk_class_decorated(ctx, ch, class_name, new_stack)
            elif ch.type == "function_definition":
                _define_method(ctx, ch, class_name, new_stack)
            elif ch.type == "class_definition":
                _define_class(ctx, ch, new_stack)

    if supers:
        for base_name in _class_bases(ctx.source, supers):
            bid = f"external::class::{base_name}"
            store.add_node(
                id=bid,
                name=base_name,
                type="import",
                file_path=None,
                start_line=None,
                end_line=None,
                complexity=1,
                metadata={"external": True},
            )
            store.add_edge(cid, bid, "INHERITS")


def _class_bases(source: bytes, supers: Node | None) -> list[str]:
    if supers is None:
        return []
    out: list[str] = []
    for c in supers.children:
        if c.type in ("identifier", "attribute"):
            out.append(_attribute_path(source, c) if c.type == "attribute" else _text(source, c))
        elif c.type == "argument_list":
            for a in c.children:
                if a.type in ("identifier", "attribute"):
                    out.append(
                        _attribute_path(source, a) if a.type == "attribute" else _text(source, a)
                    )
    return [x for x in out if x and x not in "()"]


def _walk_class_decorated(ctx: _DefContext, node: Node, class_name: str, class_stack: list[str]) -> None:
    decs: list[str] = []
    subject: Node | None = None
    for c in node.children:
        if c.type == "decorator":
            decs.append(_decorator_name(ctx.source, c))
        elif c.type in ("function_definition", "class_definition"):
            subject = c
            break
    if subject is None:
        return
    if subject.type == "class_definition":
        _define_class(ctx, subject, class_stack, pending_decorators=decs)
    else:
        _define_method(ctx, subject, class_name, class_stack, pending_decorators=decs)


def _define_method(
    ctx: _DefContext,
    node: Node,
    class_name: str,
    class_stack: list[str],
    pending_decorators: list[str] | None = None,
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    mname = _text(ctx.source, name_node)
    mid = f"{ctx.rel}::{class_name}.{mname}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    cid = f"{ctx.rel}::{class_name}"
    meta = _func_meta(ctx.source, node)
    ctx.store.add_node(
        id=mid,
        name=f"{class_name}.{mname}",
        type="method",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata=meta,
    )
    ctx.store.add_edge(cid, mid, "DEFINES")
    if pending_decorators:
        for d in pending_decorators:
            did = _decorator_node_id(ctx.rel, d)
            _ensure_decorator_node(ctx.store, did, d, ctx.rel)
            ctx.store.add_edge(did, mid, "DECORATES")


def _define_function(
    ctx: _DefContext,
    node: Node,
    class_stack: list[str],
    pending_decorators: list[str] | None = None,
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    fname = _text(ctx.source, name_node)
    fid = f"{ctx.rel}::{fname}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    meta = _func_meta(ctx.source, node)
    ctx.store.add_node(
        id=fid,
        name=fname,
        type="function",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata=meta,
    )
    ctx.store.add_edge(ctx.file_id, fid, "DEFINES")
    if pending_decorators:
        for d in pending_decorators:
            did = _decorator_node_id(ctx.rel, d)
            _ensure_decorator_node(ctx.store, did, d, ctx.rel)
            ctx.store.add_edge(did, fid, "DECORATES")

    body = node.child_by_field_name("body")
    if body:
        for ch in body.children:
            if ch.type == "function_definition":
                _define_nested_function(ctx, ch, parent_stack=[fname])
            elif ch.type == "class_definition":
                _define_class(ctx, ch, class_stack)


def _define_nested_function(ctx: _DefContext, node: Node, parent_stack: list[str]) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    fname = _text(ctx.source, name_node)
    qual = ".".join(parent_stack + [fname])
    fid = f"{ctx.rel}::{qual}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    meta = _func_meta(ctx.source, node)
    ctx.store.add_node(
        id=fid,
        name=qual,
        type="function",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata=meta,
    )
    parent_id = f"{ctx.rel}::{'.'.join(parent_stack)}"
    ctx.store.add_edge(parent_id, fid, "DEFINES")

    body = node.child_by_field_name("body")
    if body:
        for ch in body.children:
            if ch.type == "function_definition":
                _define_nested_function(ctx, ch, parent_stack=parent_stack + [fname])


def _func_meta(source: bytes, node: Node) -> dict:
    params = node.child_by_field_name("parameters")
    ret = node.child_by_field_name("return_type")
    meta: dict = {}
    if params:
        meta["params"] = _text(source, params)
    if ret:
        meta["returns"] = _text(source, ret)
    return meta


def _decorator_node_id(rel: str, d: str) -> str:
    safe = d.replace(".", "_").replace(" ", "_")
    return f"{rel}::@{safe}"


def _ensure_decorator_node(store: GraphStore, nid: str, d: str, rel: str) -> None:
    store.add_node(
        id=nid,
        name=f"@{d}",
        type="function",
        file_path=rel,
        start_line=None,
        end_line=None,
        complexity=1,
        metadata={"decorator": True},
    )


def _import_edges(ctx: _DefContext, node: Node) -> None:
    if node.type == "import_statement":
        for c in node.children:
            if c.type == "dotted_name":
                mod = _text(ctx.source, c)
                iid = f"{ctx.rel}::import::{mod}"
                ctx.store.add_node(
                    id=iid,
                    name=mod,
                    type="import",
                    file_path=ctx.rel,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    complexity=1,
                    metadata={"module": mod},
                )
                ctx.store.add_edge(ctx.file_id, iid, "IMPORTS")
            elif c.type == "aliased_import":
                dn = c.child_by_field_name("name")
                if dn and dn.type == "dotted_name":
                    mod = _text(ctx.source, dn)
                    iid = f"{ctx.rel}::import::{mod}"
                    ctx.store.add_node(
                        id=iid,
                        name=mod,
                        type="import",
                        file_path=ctx.rel,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        complexity=1,
                        metadata={"module": mod},
                    )
                    ctx.store.add_edge(ctx.file_id, iid, "IMPORTS")
    elif node.type == "import_from_statement":
        mod_node = node.child_by_field_name("module_name")
        module = _text(ctx.source, mod_node) if mod_node else ""
        for c in node.children:
            if c.type != "aliased_import":
                continue
            an = c.child_by_field_name("name")
            sym = _text(ctx.source, an) if an else ""
            alias = c.child_by_field_name("alias")
            local = _text(ctx.source, alias) if alias else sym
            iid = f"{ctx.rel}::import::{module}.{sym or '*'}"
            ctx.store.add_node(
                id=iid,
                name=f"{sym or '*'} from {module}",
                type="import",
                file_path=ctx.rel,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                complexity=1,
                metadata={"module": module, "symbol": sym, "local": local},
            )
            ctx.store.add_edge(ctx.file_id, iid, "IMPORTS")
