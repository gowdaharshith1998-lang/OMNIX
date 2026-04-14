"""OMNIX Quantum Entanglement Parser — detects tightly coupled code pairs."""

from __future__ import annotations

import os
import re

from src.graph.store import GraphStore
from src.parser import should_skip_dir

MAX_ENTANGLED_EDGES = 100


def parse_entanglements(root_path: str, store: GraphStore) -> int:
    """
    Detect code pairs that must change together.
    Creates 'ENTANGLED' edges between them.
    Returns count of entangled edges created.
    """
    root_path = os.path.abspath(root_path)
    count = 0

    backend_routes = _find_backend_routes(root_path)
    frontend_calls = _find_frontend_api_calls(root_path)

    for _fpath, route_list in backend_routes.items():
        if count >= MAX_ENTANGLED_EDGES:
            break
        for route in route_list:
            if count >= MAX_ENTANGLED_EDGES:
                break
            source_id = f"{route['file']}::{route['func']}"
            for _cfile, call_list in frontend_calls.items():
                if count >= MAX_ENTANGLED_EDGES:
                    break
                for call in call_list:
                    if _routes_match(route["path"], call["path"]):
                        target_id = call["file"]
                        if store.add_edge(
                            source_id,
                            target_id,
                            "ENTANGLED",
                            metadata={
                                "kind": "api_consumer",
                                "route": route["path"],
                                "reason": "API response shape change breaks frontend",
                            },
                        ):
                            count += 1
                        if count >= MAX_ENTANGLED_EDGES:
                            break

    models = _find_model_definitions(root_path)
    if count < MAX_ENTANGLED_EDGES:
        for model_file, model_names in models.items():
            if count >= MAX_ENTANGLED_EDGES:
                break
            for dirpath, dirnames, filenames in os.walk(root_path):
                if count >= MAX_ENTANGLED_EDGES:
                    break
                dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
                if "migrations" not in dirpath and "alembic" not in dirpath:
                    continue
                for fname in filenames:
                    if count >= MAX_ENTANGLED_EDGES:
                        break
                    if not fname.endswith(".py"):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    rel = os.path.relpath(fpath, root_path).replace(os.sep, "/")
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except OSError:
                        continue
                    low = content.lower()
                    for model_name in model_names:
                        if model_name.lower() in low:
                            if store.add_edge(
                                model_file,
                                rel,
                                "ENTANGLED",
                                metadata={
                                    "kind": "schema_model",
                                    "model": model_name,
                                    "reason": "Schema change requires migration update",
                                },
                            ):
                                count += 1
                            break

    if count < MAX_ENTANGLED_EDGES:
        count += _find_circular_imports(root_path, store, MAX_ENTANGLED_EDGES - count)

    store.commit()
    return count


def _find_backend_routes(root_path: str) -> dict[str, list[dict[str, str]]]:
    """Find FastAPI/Flask routes."""
    routes: dict[str, list[dict[str, str]]] = {}
    dec_re = re.compile(
        r'@(?:router|app)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']\s*\)',
    )
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root_path).replace(os.sep, "/")
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            out: list[dict[str, str]] = []
            for m in dec_re.finditer(content):
                rest = content[m.end() : m.end() + 1200]
                fm = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", rest)
                func = fm.group(1) if fm else "unknown"
                out.append(
                    {
                        "method": m.group(1),
                        "path": m.group(2),
                        "func": func,
                        "file": rel,
                    }
                )
            if out:
                routes[rel] = out
    return routes


def _find_frontend_api_calls(root_path: str) -> dict[str, list[dict[str, str]]]:
    """Find frontend fetch/axios calls to API endpoints."""
    calls: dict[str, list[dict[str, str]]] = {}
    fetch_pattern = re.compile(
        r'(?:fetch|axios\.?\w*|api\.?\w*)\s*\(\s*[`"\']([^`"\']*?(?:/api/|/auth/|/projects/|/executions/)[^`"\']*)[`"\']',
    )
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fname in filenames:
            if not (fname.endswith(".ts") or fname.endswith(".tsx") or fname.endswith(".js")):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root_path).replace(os.sep, "/")
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            matches = fetch_pattern.findall(content)
            if matches:
                calls[rel] = [{"path": m, "file": rel} for m in matches]
    return calls


def _routes_match(backend_path: str, frontend_path: str) -> bool:
    """Check if a backend route matches a frontend API call."""
    bp = re.sub(r"\{[^}]+\}", "*", backend_path)
    fp = re.sub(r"\$\{[^}]+\}", "*", frontend_path)
    fp = re.sub(r"https?://[^/]+", "", fp)
    bp = bp.split("?")[0]
    fp = fp.split("?")[0]
    return bp == fp or bp in fp or fp in bp


def _find_model_definitions(root_path: str) -> dict[str, list[str]]:
    """Find SQLAlchemy model class definitions."""
    models: dict[str, list[str]] = {}
    model_pattern = re.compile(
        r"class\s+(\w+)\s*\([^)]*(?:Base|Model|DeclarativeBase)[^)]*\)",
    )
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root_path).replace(os.sep, "/")
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            found = model_pattern.findall(content)
            if found:
                models[rel] = found
    return models


def _find_circular_imports(root_path: str, store: GraphStore, budget: int) -> int:
    """Find files that import each other (circular dependencies)."""
    inserted = 0
    import_pattern = re.compile(
        r'from\s+["\']?([^"\'\s;]+)["\']?\s+import|import\s+["\']?([^"\'\s;]+)',
    )
    import_map: dict[str, set[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fname in filenames:
            if not (fname.endswith(".py") or fname.endswith(".ts") or fname.endswith(".tsx")):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root_path).replace(os.sep, "/")
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            imports: set[str] = set()
            for m in import_pattern.finditer(content):
                imp = m.group(1) or m.group(2)
                if imp:
                    imports.add(imp)
            import_map[rel] = imports

    def norm_path_key(path: str) -> str:
        return path.replace(".py", "").replace(".ts", "").replace(".tsx", "").replace("/", ".")

    def file_in_import(imp: str, other_rel: str) -> bool:
        base = os.path.basename(other_rel)
        stem_py = base.replace(".py", "").replace(".ts", "").replace(".tsx", "")
        if stem_py and stem_py in imp:
            return True
        dotted = norm_path_key(other_rel)
        return dotted in imp or imp.endswith("." + stem_py)

    checked: set[tuple[str, str]] = set()
    for file_a, imports_a in import_map.items():
        if inserted >= budget:
            break
        for file_b, imports_b in import_map.items():
            if inserted >= budget:
                break
            if file_a == file_b:
                continue
            pair = tuple(sorted([file_a, file_b]))
            if pair in checked:
                continue
            checked.add(pair)

            a_imports_b = any(file_in_import(imp, file_b) for imp in imports_a)
            b_imports_a = any(file_in_import(imp, file_a) for imp in imports_b)

            if a_imports_b and b_imports_a:
                if store.add_edge(
                    file_a,
                    file_b,
                    "ENTANGLED",
                    metadata={
                        "kind": "circular_import",
                        "reason": "Circular dependency — changes to either may break the other",
                    },
                ):
                    inserted += 1
    return inserted
