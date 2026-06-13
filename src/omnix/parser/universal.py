"""Universal Tree-sitter → graph extraction (Layers 1–2). P11: do not import-edit python_parser/typescript_parser modules."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

from tree_sitter import Language, Node

from omnix.graph.store import GraphStore
from omnix.parser.hint_loader import MergedHints, load_merged_hints
from omnix.parser.memory_graph import MemoryGraphStore
from omnix.parser.tree_parse_cache import get_shared_parser, parse_tree_cached

_GraphSink = GraphStore | MemoryGraphStore


def _text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _lines_for_node(source: bytes, node: Node) -> int:
    return node.end_point[0] - node.start_point[0] + 1


def ingest_universal_to_store(
    store: _GraphSink,
    rel: str,
    text: str,
    logical_lang: str,
    language: Language,
    *,
    parse_mode: str = "generic",
    merged_hints: MergedHints | None = None,
    is_tsx: bool = False,
) -> None:
    """
    Ingest a single file. For Python/TypeScript, delegate to the existing
    Tree-sitter passes (P11: call-site only, no file edits) so outputs match
    ``parse_*_files`` for those languages.
    """
    if not language or not text:
        return
    m = merged_hints
    if m is None and logical_lang in ("python", "typescript", "rust", "c", "cpp"):
        m = load_merged_hints(logical_lang, parse_mode=parse_mode)

    if logical_lang == "python":
        from omnix.parser import python_parser as pp

        pp._pass1_definitions(store, rel, text)  # type: ignore[attr-defined]
        idx = pp._build_call_index(store)  # type: ignore[attr-defined]
        pp._pass2_calls(store, rel, text, idx)  # type: ignore[attr-defined]
        return

    if logical_lang == "typescript":
        from omnix.parser import typescript_parser as tp

        tp._ts_pass1(store, rel, text, is_tsx)  # type: ignore[attr-defined]
        tidx = tp._build_ts_call_index(store)  # type: ignore[attr-defined]
        tp._ts_pass2(store, rel, text, is_tsx, tidx)  # type: ignore[attr-defined]
        return

    if logical_lang == "rust" and m is not None:
        _ingest_rust(store, rel, text, language, m)
        return

    if m is not None:
        _ingest_generic_ts_tree(
            store, rel, text, language, m, logical_lang=logical_lang
        )
    return


# --- Rust (native impl + struct + calls) ---


def _fn_name_rust(n: Node, source: bytes) -> str | None:
    for c in n.children:
        if c.type == "identifier":
            return _text(source, c)
    return None


def _struct_name(n: Node, source: bytes) -> str | None:
    for c in n.children:
        if c.type in ("type_identifier", "field_identifier", "identifier"):
            return _text(source, c)
    return None


def _function_in_impl(fi: Node) -> bool:
    p1 = fi.parent
    p2 = p1.parent if p1 is not None else None
    return bool(
        p1
        and p1.type == "declaration_list"
        and p2
        and p2.type == "impl_item"
    )


def _impl_type_name(impl: Node, source: bytes) -> str | None:
    for c in impl.children:
        if c.type == "type_identifier":
            return _text(source, c)
    return None


def _ingest_rust(
    store: _GraphSink, rel: str, text: str, language: Language, m: MergedHints
) -> None:
    source = text.encode("utf-8")
    p = get_shared_parser("rust", language)
    tree = parse_tree_cached("rust", rel, p, source)
    root = tree.root_node
    lc = text.count("\n") + 1 if text else 1
    file_id = rel
    store.add_node(
        id=file_id,
        name=os.path.basename(rel),
        type="file",
        file_path=rel,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={"language": "rust", "parse_mode": m.parse_mode},
    )
    index: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for n in _iter_nodes(root):
        if n.type in m.all_class_node_types and n.type == "struct_item":
            sname = _struct_name(n, source) or "?"
            cid = f"{rel}::{sname}"
            sl, el = n.start_point[0] + 1, n.end_point[0] + 1
            store.add_node(
                id=cid,
                name=sname,
                type="class",
                file_path=rel,
                start_line=sl,
                end_line=el,
                complexity=_lines_for_node(source, n),
                metadata={"parse_mode": m.parse_mode},
            )
            store.add_edge(file_id, cid, "DEFINES")

    def _reg_fn(fid: str, display: str) -> None:
        short = display.split(".")[-1] if "." in display else display
        if "::" in display:
            short = display.split("::")[-1]
        index[short].append((fid, rel))
        parts = re.findall(r"[\w$]+|::", display)
        p2 = [p for p in parts if p != "::"]
        if len(p2) >= 2 and "::" in display:
            tail = p2[-1]
            k = f"{p2[-2]}.{tail}" if p2 else tail
            index[k].append((fid, rel))

    for n in _iter_nodes(root):
        if n.type != "function_item":
            continue
        if _function_in_impl(n):
            continue
        fname = _fn_name_rust(n, source)
        if not fname:
            continue
        fid = f"{rel}::{fname}"
        sl, el = n.start_point[0] + 1, n.end_point[0] + 1
        store.add_node(
            id=fid,
            name=fname,
            type="function",
            file_path=rel,
            start_line=sl,
            end_line=el,
            complexity=_lines_for_node(source, n),
            metadata={"parse_mode": m.parse_mode},
        )
        store.add_edge(file_id, fid, "DEFINES")
        _reg_fn(fid, fname)

    for impl in _iter_nodes(root):
        if impl.type != "impl_item":
            continue
        tname: str | None = None
        for c in impl.children:
            if c.type == "type_identifier":
                tname = _text(source, c)
                break
        if not tname:
            continue
        dl: Node | None = None
        for c in impl.children:
            if c.type == "declaration_list":
                dl = c
                break
        if dl is None:
            continue
        for ch in dl.children:
            if ch.type != "function_item":
                continue
            mname = _fn_name_rust(ch, source)
            if not mname:
                continue
            mid = f"{rel}::{tname}::{mname}"
            cid = f"{rel}::{tname}"
            sl, el = ch.start_point[0] + 1, ch.end_point[0] + 1
            store.add_node(
                id=mid,
                name=f"{tname}::{mname}",
                type="method",
                file_path=rel,
                start_line=sl,
                end_line=el,
                complexity=_lines_for_node(source, ch),
                metadata={"parse_mode": m.parse_mode},
            )
            store.add_edge(cid, mid, "DEFINES")
            _reg_fn(mid, mname)
            _reg_fn(mid, f"{tname}::{mname}")

    for n in _iter_nodes(root):
        if n.type in m.all_import_node_types or n.type == "use_declaration":
            iid = f"{rel}::import::{n.start_byte}"
            sl, el = n.start_point[0] + 1, n.end_point[0] + 1
            mod = re.sub(r"\s+", " ", _text(source, n)[:200])
            store.add_node(
                id=iid,
                name=mod,
                type="import",
                file_path=rel,
                start_line=sl,
                end_line=el,
                complexity=1,
                metadata={"module": mod, "parse_mode": m.parse_mode},
            )
            store.add_edge(file_id, iid, "IMPORTS")

    _rust_resolve_calls(store, rel, root, source, m, index)


def _build_rust_call_index(store: _GraphSink) -> dict[str, list[tuple[str, str]]]:
    """Reconstruct the Rust call index from the (merged) store's function/method
    nodes, restricted to Rust files. Mirrors ``_reg_fn``'s key scheme so the
    global cross-file pass resolves the same names as the per-file pass."""
    rust_files = {
        n.file_path
        for n in store.iter_all_nodes()
        if n.type == "file" and (n.metadata or {}).get("language") == "rust"
    }
    idx: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for n in store.iter_all_nodes():
        if n.type not in ("function", "method"):
            continue
        fp = n.file_path or ""
        if fp not in rust_files:
            continue
        name = n.name or ""
        if "::" in name:  # method node "Type::method"
            ttype, mname = name.rsplit("::", 1)
            idx[mname].append((n.id, fp))
            idx[f"{ttype}.{mname}"].append((n.id, fp))
        else:
            idx[name].append((n.id, fp))
    return idx


def _rust_resolve_calls(
    store: _GraphSink,
    rel: str,
    root: Node,
    source: bytes,
    m: MergedHints,
    index: dict[str, list[tuple[str, str]]],
) -> None:
    """Walk a Rust file's call sites and add CALLS edges resolved against
    *index*. add_edge dedups, so re-running with a global index (cross-file
    pass) only adds the edges the per-file pass could not resolve."""
    for n in _iter_nodes(root):
        if n.type not in m.all_call_node_types and n.type != "call_expression":
            continue
        if n.type == "macro_invocation":
            continue
        caller = _containing_function_id(n, rel, source)
        if not caller:
            continue
        tgt = _rust_call_target(rel, n, source, index)
        if not tgt or tgt == caller:
            continue
        store.add_edge(caller, tgt, "CALLS", metadata=None)


def _rust_resolve_calls_from_text(
    store: _GraphSink,
    rel: str,
    text: str,
    language: Language,
    m: MergedHints,
    index: dict[str, list[tuple[str, str]]],
) -> None:
    """Parse *text* and resolve its Rust calls against *index* (used by the
    global cross-file pass, which only has the file path + text)."""
    source = text.encode("utf-8")
    p = get_shared_parser("rust", language)
    root = parse_tree_cached("rust", rel, p, source).root_node
    _rust_resolve_calls(store, rel, root, source, m, index)


def _containing_function_id(
    call: Node, rel: str, source: bytes
) -> str | None:
    n: Node | None = call
    while n is not None:
        if n.type == "function_item":
            if _function_in_impl(n):
                impl = n.parent.parent  # type: ignore[union-attr]
                t = _impl_type_name(impl, source) if impl else None
                mn = _fn_name_rust(n, source)
                if t and mn:
                    return f"{rel}::{t}::{mn}"
            else:
                mn2 = _fn_name_rust(n, source)
                if mn2:
                    return f"{rel}::{mn2}"
        n = n.parent
    return None


def _iter_nodes(n: Node) -> list[Node]:
    out: list[Node] = [n]
    i = 0
    while i < len(out):
        out.extend(out[i].children)
        i += 1
    return out


def _rust_call_target(
    rel: str, call: Node, source: bytes, index: dict[str, list[tuple[str, str]]]
) -> str | None:
    if not call.children:
        return None
    fn0 = call.children[0]
    if fn0.type == "scoped_identifier":
        s = _text(source, fn0)
        # Resolve `path::to::func` by its tail segment against the index
        # (same-file preferred, then any file). This is what makes a
        # cross-module Rust call link to the callee's real node instead of
        # the old hardcoded same-file `rel::path::to::func` phantom id.
        tail = s.split("::")[-1]
        cands = index.get(tail)
        if cands:
            for nid, fp in cands:
                if fp == rel:
                    return nid
            return cands[0][0]
        if "::" in s:
            return f"{rel}::{s}"
    if fn0.type == "field_expression":
        last = _text(source, fn0).split(".")[-1]
        cands = index.get(last)
        if cands:
            for nid, fp in cands:
                if fp == rel:
                    return nid
        return cands[0][0] if cands else None
    if fn0.type == "identifier":
        short = _text(source, fn0)
        c2 = index.get(short)
        if c2:
            for nid, fp in c2:
                if fp == rel:
                    return nid
            return c2[0][0]
    return None


# --- Other languages: best-effort generic walk ---


def _ingest_generic_ts_tree(
    store: _GraphSink,
    rel: str,
    text: str,
    language: Language,
    m: MergedHints,
    *,
    logical_lang: str,
) -> None:
    source = text.encode("utf-8")
    p = get_shared_parser(logical_lang, language)
    root = parse_tree_cached(logical_lang, rel, p, source).root_node
    lc = text.count("\n") + 1 if text else 1
    file_id = rel
    store.add_node(
        id=file_id,
        name=os.path.basename(rel),
        type="file",
        file_path=rel,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={"parse_mode": m.parse_mode},
    )
    n_fn = 0
    for n in _iter_nodes(root):
        if n.type in m.all_function_node_types:
            name = _guess_decl_name(n, source) or f"node_{n.start_byte}"
            fid = f"{rel}::fn_{n_fn}"
            n_fn += 1
            sl, el = n.start_point[0] + 1, n.end_point[0] + 1
            store.add_node(
                id=fid,
                name=name,
                type="function",
                file_path=rel,
                start_line=sl,
                end_line=el,
                complexity=_lines_for_node(source, n),
                metadata={"parse_mode": m.parse_mode},
            )
            store.add_edge(file_id, fid, "DEFINES")


def _guess_decl_name(n: Node, source: bytes) -> str | None:
    fn = n.child_by_field_name("name")
    if fn:
        return _text(source, fn)
    for c in n.children:
        if c.type in ("identifier", "type_identifier", "field_identifier"):
            return _text(source, c)
    return None


def _count_syntactic_node_types(
    grammar: str, language: Language | None, text: str, file_path: str
) -> dict[str, int]:
    """Count Tree-sitter node `type` occurrences (full tree) for per-grammar quality."""
    if not language or not text or not file_path:
        return {}
    try:
        source = text.encode("utf-8")
        p = get_shared_parser(grammar, language)
        root = parse_tree_cached(grammar, file_path, p, source).root_node
    except (OSError, ValueError, RuntimeError):
        return {}
    c: dict[str, int] = defaultdict(int)
    for n in _iter_nodes(root):
        c[n.type] += 1
    return dict(c)


def parse_stats_for_universal_ingest(
    store: _GraphSink,
    rel: str,
    text: str,
    *,
    grammar: str = "",
    language: Language | None = None,
    is_tsx: bool = False,
) -> dict[str, Any]:
    """
    Summarize the graph + optional full-tree node counts for quality scoring
    (``parse_mode``-agnostic; ``is_tsx`` reserved for call sites that care).
    """
    _ = is_tsx  # grammar + ``language`` already identify TSX vs TS parser
    nodes = list(store.iter_nodes_by_file(rel))
    n_call_edges = store.count_call_edges_for_file(rel)
    n_fn = len([1 for n in nodes if n.type in ("function", "method")])
    n_cl = len([1 for n in nodes if n.type == "class"])
    n_im = len([1 for n in nodes if n.type == "import"])
    names = tuple(
        n.name
        for n in nodes
        if n.type in ("function", "method", "class") and n.name
    )
    type_decl_name_list: list[str] = []
    n_iface = n_talias = n_enum = 0
    for n in nodes:
        if n.type != "type_decl" or not n.metadata:
            continue
        meta = n.metadata
        if meta.get("node_kind") != "type_decl":
            continue
        dk = str(meta.get("decl_kind", ""))
        if dk == "interface":
            n_iface += 1
        elif dk == "type_alias":
            n_talias += 1
        elif dk == "enum":
            n_enum += 1
        if n.name:
            type_decl_name_list.append(n.name)
    n_arrow_g = 0
    for n in nodes:
        if n.type == "function" and n.metadata and n.metadata.get("arrow") is True:
            n_arrow_g += 1
    ts_gram = f"ts{'x' if is_tsx else ''}" if grammar == "typescript" else grammar
    ctree = (
        _count_syntactic_node_types(ts_gram, language, text, rel) if language else {}
    )
    n_arrow = max(int(ctree.get("arrow_function", 0)), n_arrow_g)
    n_iface = max(n_iface, int(ctree.get("interface_declaration", 0)))
    n_talias = max(n_talias, int(ctree.get("type_alias_declaration", 0)))
    n_enum = max(n_enum, int(ctree.get("enum_declaration", 0)))

    n_function_item = int(ctree.get("function_item", 0))
    n_impl_item = int(ctree.get("impl_item", 0))
    n_struct_item = int(ctree.get("struct_item", 0))
    n_trait_item = int(ctree.get("trait_item", 0))
    n_use_decl = int(ctree.get("use_declaration", 0))
    n_struct_type = int(ctree.get("struct_type", 0))
    n_iface_type = int(ctree.get("interface_type", 0))
    n_func_decl = int(ctree.get("function_declaration", 0))
    n_meth_decl = int(ctree.get("method_declaration", 0))
    n_imp_decl = int(ctree.get("import_declaration", 0))
    n_fn = max(
        n_fn,
        int(ctree.get("function_declaration", 0)),
        int(ctree.get("function_definition", 0)),
    )
    n_cl = max(n_cl, int(ctree.get("class_declaration", 0)))
    n_im = max(n_im, n_imp_decl, n_use_decl)

    return {
        "n_functions": n_fn,
        "n_classes": n_cl,
        "n_imports": n_im,
        "n_call_edges": n_call_edges,
        "n_lines": text.count("\n") + 1 if text else 0,
        "function_class_names": names,
        "n_interface_declaration": n_iface,
        "n_type_alias_declaration": n_talias,
        "n_enum_declaration": n_enum,
        "n_arrow_function": n_arrow,
        "n_function_declaration": n_func_decl,
        "n_method_declaration": n_meth_decl,
        "n_struct_type": n_struct_type,
        "n_interface_type": n_iface_type,
        "n_import_declaration": n_imp_decl,
        "n_function_item": n_function_item,
        "n_impl_item": n_impl_item,
        "n_struct_item": n_struct_item,
        "n_trait_item": n_trait_item,
        "n_use_declaration": n_use_decl,
        "type_decl_names": tuple(type_decl_name_list),
    }
