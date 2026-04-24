# Compliance: P11, P12, P13, P14, P15, P16, P17, P20, P21

"""
src/scan/scanner.py — scan logic

Compliance: P11, P12, P13, P14, P15, P16, P17, P20, P21
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import patterns

_MAX_FILE = 1024 * 1024
_MAX_FILES = 20
_OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
_OLLAMA_TIMEOUT = 0.5

_DOTENV_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _parse_dotenv_value(raw: str) -> str:
    s = raw.rstrip()
    if len(s) >= 2 and s[0] in "\"'" and s[0] == s[-1]:
        return s[1:-1]
    return s.lstrip()


def is_dotenv_git_tracked(project_root: Path) -> bool:
    r = subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "ls-files",
            "--error-unmatch",
            ".env",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return r.returncode == 0


def _in_git_path(path: Path) -> bool:
    return ".git" in path.resolve().parts


def is_allowed_file_path(
    candidate: Path,
    home: Path,
    project_root: Path,
) -> bool:
    """
    C2: resolved path must be under a fixed allowlist; reject symlink escape
    and any path with a .git path component.
    """
    try:
        rp = candidate.resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    if _in_git_path(rp):
        return False
    penv = (project_root / ".env").resolve()
    oenv = (home / ".omnix" / "detected_keys.env").resolve()
    if rp == penv or rp == oenv:
        return True
    allow = [
        (home / ".anthropic").resolve(),
        (home / ".config" / "anthropic").resolve(),
        (home / ".config" / "openai").resolve(),
        (home / ".config" / "google-genai").resolve(),
        (home / ".config" / "gemini").resolve(),
    ]
    for r in allow:
        if r.is_dir():
            try:
                if rp == r or rp.is_relative_to(r):
                    return True
            except (OSError, ValueError):
                pass
    return False


def _name_matches_scan(name: str) -> bool:
    n = name
    for pat in (
        "config*",
        "credentials*",
        "credentials",
        "*.env",
        "*.json",
        "*.yaml",
        "*.yml",
        "*.toml",
    ):
        if fnmatch.fnmatch(n, pat):
            return True
    return name.startswith("config") or name == "credentials"


def _home_display(path: Path, home: Path) -> str:
    try:
        rel = path.resolve().relative_to(home.resolve())
        return f"~/{rel.as_posix()}"
    except ValueError:
        return str(path)


def _read_text_file(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    if st.st_size > _MAX_FILE:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _iter_scan_dir(
    d: Path,
    home: Path,
    project_root: Path,
) -> list[tuple[str, str, str]]:
    """Top-level only; max 20 files; (provider, value, source_str)."""
    out: list[tuple[str, str, str]] = []
    if not d.is_dir():
        return out
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    n_ok = 0
    for name in names:
        if n_ok >= _MAX_FILES:
            break
        c = d / name
        try:
            if not c.is_file():
                continue
        except OSError:
            continue
        if not _name_matches_scan(name):
            continue
        if not is_allowed_file_path(c, home, project_root):
            continue
        text = _read_text_file(c)
        if text is None:
            continue
        n_ok += 1
        for line_i, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = _DOTENV_KEY.match(s)
            if not m:
                continue
            value = _parse_dotenv_value(m.group(2))
            prov = patterns.classify_credential(value)
            if prov:
                src = f"file:{_home_display(c, home)}:{line_i}"
                out.append((prov, value, src))
    return out


def _scan_file_plain(
    path: Path,
    home: Path,
    project_root: Path,
    sources: list[str],
) -> list[tuple[str, str, str]]:
    if not is_allowed_file_path(path, home, project_root):
        return []
    display = "file:./.env" if path.resolve() == (project_root / ".env").resolve() else f"file:{_home_display(path, home)}"
    sources.append(display)
    text = _read_text_file(path)
    if not text:
        return []
    out: list[tuple[str, str, str]] = []
    for line_i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _DOTENV_KEY.match(s)
        if not m:
            continue
        value = _parse_dotenv_value(m.group(2))
        prov = patterns.classify_credential(value)
        if prov:
            pfx = (
                "file:./.env"
                if path.resolve() == (project_root / ".env").resolve()
                else f"file:{_home_display(path, home)}"
            )
            out.append((prov, value, f"{pfx}:{line_i}"))
    return out


def _probe_ollama() -> bool:
    try:
        req = urllib.request.Request(  # noqa: S310 — fixed localhost
            _OLLAMA_URL,
            method="GET",
        )
        with urllib.request.urlopen(  # noqa: S310
            req, timeout=_OLLAMA_TIMEOUT
        ) as r:
            return r.getcode() == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False



def run_scan(
    project_root: Path,
    home: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """
    Return (candidates, sources_scanned, reasons_skip).
    Each candidate: { provider, key_value, key_length, source } (plaintext key).
    """
    home = home or Path.home()
    project_root = project_root.resolve()
    sources: list[str] = []
    reasons: list[str] = []
    raw: list[tuple[str, str, str, int]] = []

    sources.append("env:process_environment")
    for k, v in os.environ.items():
        prov = patterns.classify_credential(v)
        if prov:
            raw.append((prov, v, f"env:{k}", len(v)))

    penv = project_root / ".env"
    if penv.is_file():
        if is_dotenv_git_tracked(project_root):
            reasons.append("skipped_git_tracked:project .env")
        elif is_allowed_file_path(penv, home, project_root):
            for pr, val, so in _scan_file_plain(
                penv, home, project_root, sources
            ):
                raw.append((pr, val, so, len(val)))

    for label, d in (
        (".anthropic", home / ".anthropic"),
        (".config/anthropic", home / ".config" / "anthropic"),
        (".config/openai", home / ".config" / "openai"),
        (".config/google-genai", home / ".config" / "google-genai"),
        (".config/gemini", home / ".config" / "gemini"),
    ):
        if d.is_dir():
            sources.append(f"dir:{label}")
            for pr, val, so in _iter_scan_dir(d, home, project_root):
                raw.append((pr, val, so, len(val)))

    det = home / ".omnix" / "detected_keys.env"
    if det.is_file() and is_allowed_file_path(det, home, project_root):
        for pr, val, so in _scan_file_plain(
            det, home, project_root, sources
        ):
            raw.append((pr, val, so, len(val)))

    if _probe_ollama():
        sources.append("probe:ollama-localhost")
        raw.append(
            (
                "ollama",
                "",
                "probe:ollama-localhost",
                0,
            )
        )
    else:
        sources.append("probe:ollama-localhost(offline)")

    cands: list[dict[str, Any]] = []
    for pr, v, so, kl in raw:
        cands.append(
            {
                "provider": pr,
                "key_value": v,
                "key_length": int(kl) if not (pr == "ollama" and v == "") else 0,
                "source": so,
            }
        )
    return cands, sources, reasons

