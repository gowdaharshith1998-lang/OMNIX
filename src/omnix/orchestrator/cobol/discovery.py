"""COBOL program, copybook, and fixture discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_COBOL_EXTENSIONS = {".cob", ".cbl", ".cobol"}
_COPYBOOK_EXTENSIONS = {".cpy"}
_SKIP_DIRS = {".git", ".omnix", "__pycache__", "node_modules"}
_PROGRAM_RE = re.compile(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", re.IGNORECASE)
_COPY_RE = re.compile(r"\bCOPY\s+['\"]?([A-Z0-9_-]+)['\"]?", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveredProgram:
    program_id: str
    source_path: Path
    copybook_paths: list[Path]
    fixture_paths: list[Path]
    node_id: str | None


@dataclass(frozen=True)
class Discovery:
    codebase_root: Path
    programs: list[DiscoveredProgram]
    orphan_copybooks: list[Path]
    orphan_fixtures: list[Path]


def discover(codebase_root: Path, *, fixtures_root: Path | None = None) -> Discovery:
    root = codebase_root.resolve()
    programs: list[DiscoveredProgram] = []
    copybooks = _find_files(root, _COPYBOOK_EXTENSIONS)
    copybook_by_stem = {p.stem.upper(): p for p in copybooks}
    referenced_copybooks: set[Path] = set()

    for source in _find_files(root, _COBOL_EXTENSIONS):
        text = source.read_text(encoding="utf-8", errors="replace")
        program_id = _program_name(source, text)
        program_copybooks = _copybooks_for(text, copybook_by_stem)
        referenced_copybooks.update(program_copybooks)
        programs.append(
            DiscoveredProgram(
                program_id=program_id,
                source_path=source,
                copybook_paths=program_copybooks,
                fixture_paths=_fixture_paths(root, program_id, fixtures_root),
                node_id=_node_id_for(root, source, program_id),
            )
        )

    used_fixtures = {p.resolve() for program in programs for p in program.fixture_paths}
    orphan_fixtures = [
        p for p in _all_fixture_candidates(root, fixtures_root) if p.resolve() not in used_fixtures
    ]
    return Discovery(
        codebase_root=root,
        programs=sorted(programs, key=lambda p: p.program_id),
        orphan_copybooks=sorted((p for p in copybooks if p not in referenced_copybooks), key=_sort_key),
        orphan_fixtures=sorted(orphan_fixtures, key=_sort_key),
    )


def _find_files(root: Path, extensions: set[str]) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if _is_excluded(path, root):
            continue
        if path.is_file() and path.suffix.lower() in extensions:
            out.append(path)
    return sorted(out, key=_sort_key)


def _is_excluded(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in _SKIP_DIRS for part in rel.parts)


def _program_name(path: Path, text: str) -> str:
    match = _PROGRAM_RE.search(text)
    return (match.group(1) if match else path.stem).upper()


def _copybooks_for(text: str, copybook_by_stem: dict[str, Path]) -> list[Path]:
    found: list[Path] = []
    for match in _COPY_RE.finditer(text):
        path = copybook_by_stem.get(match.group(1).upper())
        if path is not None and path not in found:
            found.append(path)
    return sorted(found, key=_sort_key)


def _fixture_paths(root: Path, program_id: str, fixtures_root: Path | None) -> list[Path]:
    candidates: list[Path] = []
    inputs = root / "inputs"
    if inputs.is_dir():
        candidates.extend(_case_insensitive_matches(inputs, f"{program_id}.in"))
    if fixtures_root is not None and fixtures_root.is_dir():
        candidates.extend(_case_insensitive_matches(fixtures_root, f"{program_id}.in"))
        program_dir = _case_insensitive_dir(fixtures_root, program_id)
        if program_dir is not None:
            candidates.extend(_fixture_children(program_dir))
    default_dir = _case_insensitive_dir(root / "fixtures", program_id)
    if default_dir is not None:
        candidates.extend(_fixture_children(default_dir))
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.resolve().as_posix()
        if key not in seen:
            deduped.append(candidate)
            seen.add(key)
    return sorted(deduped, key=_sort_key)


def _all_fixture_candidates(root: Path, fixtures_root: Path | None) -> list[Path]:
    roots = [root / "inputs", root / "fixtures"]
    if fixtures_root is not None:
        roots.append(fixtures_root)
    out: list[Path] = []
    for base in roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and (path.suffix.lower() == ".in" or path.name == "input.bin"):
                out.append(path)
    return out


def _case_insensitive_matches(root: Path, filename: str) -> list[Path]:
    wanted = filename.lower()
    return sorted((p for p in root.iterdir() if p.is_file() and p.name.lower() == wanted), key=_sort_key)


def _case_insensitive_dir(root: Path, dirname: str) -> Path | None:
    if not root.is_dir():
        return None
    wanted = dirname.lower()
    for child in sorted(root.iterdir(), key=_sort_key):
        if child.is_dir() and child.name.lower() == wanted:
            return child
    return None


def _fixture_children(program_dir: Path) -> list[Path]:
    children = [p for p in program_dir.iterdir() if p.is_file() or p.is_dir()]
    return sorted(children, key=_sort_key)


def _node_id_for(root: Path, source: Path, program_id: str) -> str:
    try:
        rel = source.relative_to(root).as_posix()
    except ValueError:
        rel = source.as_posix()
    return f"{rel}::CobolProgram::{program_id}"


def _sort_key(path: Path) -> str:
    return path.as_posix().lower()

