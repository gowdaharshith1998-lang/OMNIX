"""Tree-sitter extraction for TypeScript / TSX sources."""

from __future__ import annotations  # must stay first: forward refs in helpers

import os
from collections import defaultdict

from tree_sitter import Language, Node, Parser
import tree_sitter_typescript as tst

from src.graph.store import GraphStore
from src.parser import should_skip_dir
from src.parser.tree_parse_cache import get_shared_parser, parse_tree_cached

_TS_LANG = Language(tst.language_typescript())
_TSX_LANG = Language(tst.language_tsx())


def _parser_ts() -> Parser:
    return get_shared_parser("ts", _TS_LANG)


def _parser_tsx() -> Parser:
    return get_shared_parser("tsx", _TSX_LANG)


def _text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _lines_for_node(source: bytes, node: Node) -> int:
    return node.end_point[0] - node.start_point[0] + 1


def parse_typescript_files(root: str, store: GraphStore) -> int:
    root = os.path.abspath(root)
    count = 0
    files: list[tuple[str, str, bool]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fn in filenames:
            if fn.endswith(".d.ts"):
                continue
            is_tsx = fn.endswith(".tsx")
            if not (fn.endswith(".ts") or is_tsx):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "rb") as f:
                    src = f.read()
            except OSError:
                continue
            files.append((rel, src.decode("utf-8", errors="replace"), is_tsx))
            count += 1

    for rel, text, is_tsx in files:
        _ts_pass1(store, rel, text, is_tsx)
    index = _build_ts_call_index(store)
    for rel, text, is_tsx in files:
        _ts_pass2(store, rel, text, is_tsx, index)
    store.commit()
    return count


def _build_ts_call_index(store: GraphStore) -> dict[str, list[tuple[str, str]]]:
    by_short: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for n in store.iter_all_nodes():
        if n.type not in ("function", "method"):
            continue
        short = n.name.split(".")[-1]
        fp = n.file_path or ""
        by_short[short].append((n.id, fp))
    return by_short


def _ts_add_type_decl_for_stats(
    ctx: _TsDefCtx, node: Node, decl_kind: str, parent_id: str
) -> None:
    """
    Stats-only node for type declarations. Not in evolution mutation set (P21);
    ``type`` is ``type_decl`` with ``metadata['node_kind'] == 'type_decl'``.
    """
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    if name_node.type not in ("identifier", "type_identifier"):
        return
    name = _text(ctx.source, name_node)
    if not name:
        return
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    tid = f"{ctx.rel}::tdecl_{decl_kind}::{name}::{node.start_byte}"
    ctx.store.add_node(
        id=tid,
        name=name,
        type="type_decl",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata={"node_kind": "type_decl", "decl_kind": decl_kind},
    )
    ctx.store.add_edge(parent_id, tid, "DEFINES")


def _ts_pass1(store: GraphStore, rel: str, text: str, is_tsx: bool) -> None:
    source = text.encode("utf-8")
    g = "tsx" if is_tsx else "ts"
    parser = _parser_tsx() if is_tsx else _parser_ts()
    tree = parse_tree_cached(g, rel, parser, source)
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
        metadata={"language": "tsx" if is_tsx else "typescript"},
    )
    ctx = _TsDefCtx(store=store, file_id=file_id, rel=rel, source=source)
    for ch in tree.root_node.children:
        _ts_pass1_statement(ctx, ch, parent_id=file_id, class_stack=[])


def _ts_pass1_statement(
    ctx: _TsDefCtx,
    stmt: Node,
    parent_id: str,
    class_stack: list[str],
) -> None:
    if stmt.type == "export_statement":
        for c in stmt.children:
            if c.type in (
                "function_declaration",
                "lexical_declaration",
                "class_declaration",
                "interface_declaration",
                "type_alias_declaration",
                "enum_declaration",
            ):
                _ts_pass1_statement(ctx, c, parent_id, class_stack)
        return
    if stmt.type == "interface_declaration":
        _ts_add_type_decl_for_stats(ctx, stmt, "interface", parent_id)
        return
    if stmt.type == "type_alias_declaration":
        _ts_add_type_decl_for_stats(ctx, stmt, "type_alias", parent_id)
        return
    if stmt.type == "enum_declaration":
        _ts_add_type_decl_for_stats(ctx, stmt, "enum", parent_id)
        return
    if stmt.type == "function_declaration":
        _ts_define_function(ctx, stmt, parent_id, class_stack)
        return
    if stmt.type == "lexical_declaration":
        for c in stmt.children:
            if c.type == "variable_declarator":
                _ts_variable_declarator(ctx, c, parent_id, class_stack)
        return
    if stmt.type == "class_declaration":
        _ts_define_class(ctx, stmt, parent_id, class_stack)
        return
    if stmt.type == "import_statement":
        _ts_imports(ctx, stmt)
        return


def _ts_variable_declarator(
    ctx: _TsDefCtx, node: Node, parent_id: str, class_stack: list[str]
) -> None:
    name_node = node.child_by_field_name("name")
    val = node.child_by_field_name("value")
    if name_node is None or val is None:
        return
    if name_node.type != "identifier":
        return
    sym = _text(ctx.source, name_node)
    if val.type == "arrow_function":
        _ts_add_function(ctx, sym, val, parent_id, class_stack, is_arrow=True)
    elif val.type == "function_expression":
        _ts_add_function(ctx, sym, val, parent_id, class_stack, is_arrow=False)


def _ts_define_function(
    ctx: _TsDefCtx, node: Node, parent_id: str, class_stack: list[str]
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    sym = _text(ctx.source, name_node)
    _ts_add_function(ctx, sym, node, parent_id, class_stack, is_arrow=False)


def _ts_add_function(
    ctx: _TsDefCtx,
    sym: str,
    node: Node,
    parent_id: str,
    class_stack: list[str],
    *,
    is_arrow: bool,
) -> None:
    fid = f"{ctx.rel}::{sym}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    meta: dict = {"arrow": is_arrow}
    params = node.child_by_field_name("parameters")
    if params:
        meta["params"] = _text(ctx.source, params)
    ret = node.child_by_field_name("return_type")
    if ret:
        meta["returns"] = _text(ctx.source, ret)
    ctx.store.add_node(
        id=fid,
        name=sym,
        type="function",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata=meta,
    )
    ctx.store.add_edge(parent_id, fid, "DEFINES")
    body = node.child_by_field_name("body")
    if body:
        _ts_pass1_block(ctx, body, fid, class_stack)


def _ts_pass1_block(ctx: _TsDefCtx, block: Node, parent_id: str, class_stack: list[str]) -> None:
    for ch in block.children:
        if ch.type == "function_declaration":
            name_node = ch.child_by_field_name("name")
            if name_node:
                inner = _text(ctx.source, name_node)
                _ts_define_nested_function(ctx, ch, parent_id, class_stack, inner)
        elif ch.type == "lexical_declaration":
            for c in ch.children:
                if c.type == "variable_declarator":
                    _ts_variable_declarator(ctx, c, parent_id, class_stack)
        elif ch.type == "class_declaration":
            _ts_define_class(ctx, ch, parent_id, class_stack)


def _ts_define_nested_function(
    ctx: _TsDefCtx, node: Node, parent_id: str, class_stack: list[str], sym: str
) -> None:
    parent_qual = parent_id.split("::", 1)[-1] if "::" in parent_id else parent_id
    fid = f"{ctx.rel}::{parent_qual}.{sym}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    meta: dict = {}
    params = node.child_by_field_name("parameters")
    if params:
        meta["params"] = _text(ctx.source, params)
    ctx.store.add_node(
        id=fid,
        name=f"{parent_qual}.{sym}",
        type="function",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata=meta,
    )
    ctx.store.add_edge(parent_id, fid, "DEFINES")
    body = node.child_by_field_name("body")
    if body:
        _ts_pass1_block(ctx, body, fid, class_stack)


def _ts_define_class(
    ctx: _TsDefCtx, node: Node, parent_id: str, class_stack: list[str]
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    cname = _text(ctx.source, name_node)
    cid = f"{ctx.rel}::{cname}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    heritage = _ts_class_heritage(node)
    bases: list[str] = []
    if heritage is not None:
        bases = _ts_extends_bases(ctx.source, heritage)
    ctx.store.add_node(
        id=cid,
        name=cname,
        type="class",
        file_path=ctx.rel,
        start_line=sl,
        end_line=el,
        complexity=lines,
        metadata={"bases": bases},
    )
    ctx.store.add_edge(parent_id, cid, "DEFINES")
    for b in bases:
        bid = f"external::ts::{b}"
        ctx.store.add_node(
            id=bid,
            name=b,
            type="import",
            file_path=None,
            start_line=None,
            end_line=None,
            complexity=1,
            metadata={"external": True},
        )
        ctx.store.add_edge(cid, bid, "INHERITS")
    body = node.child_by_field_name("body")
    new_stack = class_stack + [cname]
    if body:
        for ch in body.children:
            if ch.type == "method_definition":
                _ts_define_method(ctx, ch, cid, cname, new_stack)
            elif ch.type == "class_declaration":
                _ts_define_class(ctx, ch, cid, new_stack)


def _ts_class_heritage(class_node: Node) -> Node | None:
    for c in class_node.children:
        if c.type == "class_heritage":
            return c
    return None


def _ts_extends_bases(source: bytes, heritage: Node) -> list[str]:
    out: list[str] = []
    for ch in heritage.children:
        if ch.type != "extends_clause":
            continue
        for t in ch.children:
            if t.type in ("identifier", "type_identifier", "nested_type_identifier"):
                out.append(_text(source, t).strip())
                break
    return [x for x in out if x and x not in ("extends", "implements")]


def _ts_define_method(
    ctx: _TsDefCtx, node: Node, class_id: str, class_name: str, class_stack: list[str]
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    mname = _text(ctx.source, name_node)
    mid = f"{ctx.rel}::{class_name}.{mname}"
    sl = node.start_point[0] + 1
    el = node.end_point[0] + 1
    lines = _lines_for_node(ctx.source, node)
    meta: dict = {}
    params = node.child_by_field_name("parameters")
    if params:
        meta["params"] = _text(ctx.source, params)
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
    ctx.store.add_edge(class_id, mid, "DEFINES")
    body = node.child_by_field_name("body")
    if body:
        _ts_pass1_block(ctx, body, mid, class_stack)


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _ts_imports(ctx: _TsDefCtx, stmt: Node) -> None:
    mod = ""
    for c in stmt.children:
        if c.type == "string":
            mod = _strip_quotes(_text(ctx.source, c))
            break
    clause = None
    for c in stmt.children:
        if c.type == "import_clause":
            clause = c
            break
    if not clause:
        return
    if any(ch.type == "namespace_import" for ch in clause.children):
        for ch in clause.children:
            if ch.type == "namespace_import":
                for g in ch.children:
                    if g.type == "identifier":
                        alias = _text(ctx.source, g)
                        iid = f"{ctx.rel}::import::* as {alias}::{mod}"
                        ctx.store.add_node(
                            id=iid,
                            name=f"* as {alias} from {mod}",
                            type="import",
                            file_path=ctx.rel,
                            start_line=stmt.start_point[0] + 1,
                            end_line=stmt.end_point[0] + 1,
                            complexity=1,
                            metadata={"module": mod, "namespace": alias},
                        )
                        ctx.store.add_edge(ctx.file_id, iid, "IMPORTS")
        return
    for ch in clause.children:
        if ch.type == "identifier":
            default_name = _text(ctx.source, ch)
            iid = f"{ctx.rel}::import::default::{default_name}::{mod}"
            ctx.store.add_node(
                id=iid,
                name=f"{default_name} (default) from {mod}",
                type="import",
                file_path=ctx.rel,
                start_line=stmt.start_point[0] + 1,
                end_line=stmt.end_point[0] + 1,
                complexity=1,
                metadata={"module": mod, "default": default_name},
            )
            ctx.store.add_edge(ctx.file_id, iid, "IMPORTS")
        elif ch.type == "named_imports":
            for ni in ch.children:
                if ni.type != "import_specifier":
                    continue
                orig = ni.child_by_field_name("name")
                al = ni.child_by_field_name("alias")
                sym = _text(ctx.source, orig) if orig else ""
                local = _text(ctx.source, al) if al else sym
                iid = f"{ctx.rel}::import::{mod}::{local}"
                ctx.store.add_node(
                    id=iid,
                    name=f"{sym} from {mod}",
                    type="import",
                    file_path=ctx.rel,
                    start_line=stmt.start_point[0] + 1,
                    end_line=stmt.end_point[0] + 1,
                    complexity=1,
                    metadata={"module": mod, "symbol": sym, "local": local},
                )
                ctx.store.add_edge(ctx.file_id, iid, "IMPORTS")


def _ts_pass2(
    store: GraphStore,
    rel: str,
    text: str,
    is_tsx: bool,
    index: dict[str, list[tuple[str, str]]],
) -> None:
    source = text.encode("utf-8")
    g = "tsx" if is_tsx else "ts"
    parser = _parser_tsx() if is_tsx else _parser_ts()
    tree = parse_tree_cached(g, rel, parser, source)
    ctx = _TsCallCtx(store=store, rel=rel, source=source, index=index, stack=[])
    for ch in tree.root_node.children:
        _ts_pass2_statement(ctx, ch, parent_function=None)


def _ts_pass2_statement(ctx: _TsCallCtx, stmt: Node, parent_function: str | None) -> None:
    if stmt.type == "export_statement":
        for c in stmt.children:
            if c.type in ("function_declaration", "lexical_declaration", "class_declaration"):
                _ts_pass2_statement(ctx, c, parent_function)
        return
    if stmt.type == "function_declaration":
        name_node = stmt.child_by_field_name("name")
        if name_node:
            fid = f"{ctx.rel}::{_text(ctx.source, name_node)}"
            _ts_enter_function(ctx, stmt, fid)
        return
    if stmt.type == "lexical_declaration":
        for c in stmt.children:
            if c.type != "variable_declarator":
                continue
            name_node = c.child_by_field_name("name")
            val = c.child_by_field_name("value")
            if name_node and val and name_node.type == "identifier" and val.type in (
                "arrow_function",
                "function_expression",
            ):
                sym = _text(ctx.source, name_node)
                fid = f"{ctx.rel}::{sym}"
                _ts_enter_function(ctx, val, fid)
        return
    if stmt.type == "class_declaration":
        name_node = stmt.child_by_field_name("name")
        if name_node is None:
            return
        cname = _text(ctx.source, name_node)
        body = stmt.child_by_field_name("body")
        if not body:
            return
        for ch in body.children:
            if ch.type == "method_definition":
                mn = ch.child_by_field_name("name")
                if mn:
                    mid = f"{ctx.rel}::{cname}.{_text(ctx.source, mn)}"
                    _ts_enter_function(ctx, ch, mid)
            elif ch.type == "class_declaration":
                _ts_pass2_statement(ctx, ch, parent_function)


def _ts_enter_function(ctx: _TsCallCtx, node: Node, fid: str) -> None:
    ctx.stack.append(fid)
    body = node.child_by_field_name("body")
    if body:
        _ts_scan_calls_and_jsx(ctx, body)
        for ch in body.children:
            if ch.type == "function_declaration":
                mn = ch.child_by_field_name("name")
                if mn:
                    inner = _text(ctx.source, mn)
                    parent_qual = fid.split("::", 1)[-1]
                    nested_id = f"{ctx.rel}::{parent_qual}.{inner}"
                    _ts_enter_function(ctx, ch, nested_id)
            elif ch.type == "lexical_declaration":
                for c in ch.children:
                    if c.type != "variable_declarator":
                        continue
                    nn = c.child_by_field_name("name")
                    val = c.child_by_field_name("value")
                    if nn and val and nn.type == "identifier" and val.type in (
                        "arrow_function",
                        "function_expression",
                    ):
                        sym = _text(ctx.source, nn)
                        parent_qual = fid.split("::", 1)[-1]
                        nested_id = f"{ctx.rel}::{parent_qual}.{sym}"
                        _ts_enter_function(ctx, val, nested_id)
            elif ch.type == "class_declaration":
                _ts_pass2_statement(ctx, ch, fid)
    ctx.stack.pop()


def _ts_scan_calls_and_jsx(ctx: _TsCallCtx, node: Node) -> None:
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "call_expression":
            _ts_emit_call(ctx, n)
        elif n.type in ("jsx_self_closing_element", "jsx_opening_element"):
            _ts_emit_jsx(ctx, n)
        stack.extend(reversed(n.children))


def _ts_emit_jsx(ctx: _TsCallCtx, n: Node) -> None:
    if not ctx.stack:
        return
    caller = ctx.stack[-1]
    name_el = None
    for c in n.children:
        if c.type == "identifier":
            name_el = c
            break
    if name_el is None:
        return
    tag = _text(ctx.source, name_el)
    if not tag or not tag[0].isupper():
        return
    target = _resolve_ts_callee(ctx.rel, tag, ctx.index)
    if target and target != caller:
        ctx.store.add_edge(caller, target, "CALLS")


def _ts_emit_call(ctx: _TsCallCtx, call_node: Node) -> None:
    if not ctx.stack:
        return
    caller = ctx.stack[-1]
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return
    short: str | None = None
    if fn.type == "identifier":
        short = _text(ctx.source, fn)
    elif fn.type == "member_expression":
        prop = fn.child_by_field_name("property")
        obj = fn.child_by_field_name("object")
        if prop and obj and obj.type == "identifier" and _text(ctx.source, obj) in (
            "React",
            "react",
        ):
            short = _text(ctx.source, prop)
    if not short:
        return
    if short in ("console", "require", "parseInt", "Math", "Object", "Array", "Promise"):
        return
    target = _resolve_ts_callee(ctx.rel, short, ctx.index)
    if target and target != caller:
        ctx.store.add_edge(caller, target, "CALLS")


def _resolve_ts_callee(caller_file: str, short: str, index: dict[str, list[tuple[str, str]]]) -> str | None:
    cands = index.get(short)
    if not cands:
        return None
    same = [nid for nid, fp in cands if fp == caller_file]
    if same:
        return same[0]
    return cands[0][0]


class _TsDefCtx:
    __slots__ = ("store", "file_id", "rel", "source")

    def __init__(self, store: GraphStore, file_id: str, rel: str, source: bytes) -> None:
        self.store = store
        self.file_id = file_id
        self.rel = rel
        self.source = source


class _TsCallCtx:
    __slots__ = ("store", "rel", "source", "index", "stack")

    def __init__(
        self,
        store: GraphStore,
        rel: str,
        source: bytes,
        index: dict[str, list[tuple[str, str]]],
        stack: list[str],
    ) -> None:
        self.store = store
        self.rel = rel
        self.source = source
        self.index = index
        self.stack = stack
