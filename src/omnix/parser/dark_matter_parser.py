"""OMNIX Dark Matter Parser — detects invisible dependencies."""

from __future__ import annotations

import os
import re

from omnix.graph.store import GraphStore
from omnix.parser import should_skip_dir

MAX_DARK_MATTER_NODES = 50


def parse_dark_matter(root_path: str, store: GraphStore) -> int:
    """
    Scan for dark matter: env vars, config files, middleware, decorators, constants.
    Creates 'dark_matter' nodes and 'DARK_FORCE' edges to affected modules.
    Returns count of dark matter nodes found.
    """
    root_path = os.path.abspath(root_path)
    count = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        if any(part in (".next",) for part in dirpath.split(os.sep)):
            continue

        for fname in filenames:
            if count >= MAX_DARK_MATTER_NODES:
                return count
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root_path).replace(os.sep, "/")

            if fname.startswith(".env"):
                env_vars = _parse_env_file(fpath)
                node_id = f"dark::{rel}"
                store.add_node(
                    node_id,
                    fname,
                    "dark_matter",
                    rel,
                    0,
                    0,
                    max(1, len(env_vars)),
                    metadata={"kind": "env", "vars": env_vars},
                )
                count += 1
                _link_env_consumers(root_path, node_id, env_vars, store)

            elif fname in (
                "config.py",
                "settings.py",
                "config.ts",
                "config.js",
                "constants.py",
                "constants.ts",
            ):
                constants = _parse_config_file(fpath)
                node_id = f"dark::{rel}"
                store.add_node(
                    node_id,
                    fname,
                    "dark_matter",
                    rel,
                    0,
                    0,
                    max(1, len(constants)),
                    metadata={"kind": "config", "constants": constants[:20]},
                )
                count += 1
                _link_config_consumers(root_path, node_id, fname, store)

            elif fname.endswith(".py") and "middleware" in fname.lower():
                node_id = f"dark::{rel}"
                store.add_node(
                    node_id,
                    fname,
                    "dark_matter",
                    rel,
                    0,
                    0,
                    5,
                    metadata={"kind": "middleware"},
                )
                count += 1
                _link_middleware_consumers(root_path, node_id, store)

    store.commit()
    return count


def _parse_env_file(fpath: str) -> list[str]:
    """Extract variable names from .env file."""
    names: list[str] = []
    try:
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    names.append(line.split("=", 1)[0].strip())
    except OSError:
        pass
    return names


def _parse_config_file(fpath: str) -> list[str]:
    """Extract constant/config names."""
    constants: list[str] = []
    try:
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.match(r"^([A-Z][A-Z0-9_]{2,})\s*[:=]", line)
                if m:
                    constants.append(m.group(1))
                m = re.match(r"export\s+const\s+([A-Z][A-Z0-9_]{2,})", line)
                if m:
                    constants.append(m.group(1))
    except OSError:
        pass
    return constants


def _link_env_consumers(root_path: str, dark_node_id: str, env_vars: list[str], store: GraphStore) -> None:
    """Find files that read these env vars and create DARK_FORCE edges."""
    if not env_vars:
        return
    patterns = [
        r"os\.environ",
        r"os\.getenv",
        r"process\.env\.",
        r"settings\.",
        r"config\.",
    ]
    for var in env_vars[:20]:
        patterns.append(re.escape(var))

    combined = "|".join(patterns)
    regex = re.compile(combined)

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
            if regex.search(content):
                store.add_edge(
                    dark_node_id,
                    rel,
                    "DARK_FORCE",
                    metadata={"kind": "env_dependency"},
                )


def _link_config_consumers(root_path: str, dark_node_id: str, config_fname: str, store: GraphStore) -> None:
    """Find files that import from the config file."""
    base = config_fname.rsplit(".", 1)[0]
    patterns = [
        rf"from\s+.*{re.escape(base)}\s+import",
        rf"import\s+.*{re.escape(base)}\b",
        rf"require\s*\(\s*['\"].*{re.escape(base)}",
    ]
    regex = re.compile("|".join(patterns))

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
            if regex.search(content):
                store.add_edge(
                    dark_node_id,
                    rel,
                    "DARK_FORCE",
                    metadata={"kind": "config_import"},
                )


def _link_middleware_consumers(root_path: str, dark_node_id: str, store: GraphStore) -> None:
    """Middleware affects all route/api files."""
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), root_path).replace(os.sep, "/")
            if "api/" in rel or "routes/" in rel or "router" in fname.lower():
                store.add_edge(
                    dark_node_id,
                    rel,
                    "DARK_FORCE",
                    metadata={"kind": "middleware_affect"},
                )
