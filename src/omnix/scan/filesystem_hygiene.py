"""Filesystem hygiene snapshots for PBT runs (slice 17b).

Snapshot + diff are best-effort and non-atomic relative to concurrent writers
(P17): multi-threaded targets may produce inconsistent diffs.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

_LOG = logging.getLogger("omnix.scan.filesystem_hygiene")


def _stat_triple(p: Path) -> tuple[str, int, int] | None:
    try:
        st = p.stat()
        return (
            str(p),
            int(st.st_size),
            int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
        )
    except OSError as e:
        _LOG.debug("stat failed for %s: %s", p, e)
        return None


def _walk_tree_max_depth(root: Path, max_depth: int | None) -> list[tuple[str, int, int]]:
    """Breadth-first walk using os.scandir; max_depth=None means unlimited."""
    root = root.resolve()
    out: list[tuple[str, int, int]] = []
    q: deque[tuple[Path, int]] = deque([(root, 0)])
    while q:
        d, dd = q.popleft()
        if max_depth is not None and dd > max_depth:
            continue
        try:
            with os.scandir(d) as it:
                for ent in it:
                    p = Path(ent.path)
                    child_depth = dd + 1
                    if max_depth is not None and child_depth > max_depth:
                        continue
                    trip = _stat_triple(p)
                    if trip:
                        out.append(trip)
                    if ent.is_dir(follow_symlinks=False):
                        go_deeper = max_depth is None or child_depth < max_depth
                        if go_deeper:
                            q.append((p, child_depth))
        except OSError as e:
            _LOG.debug("scandir failed for %s: %s", d, e)
    return out


def _snapshot_repo_region(repo_root: Path, max_depth: int | None) -> list[tuple[str, int, int]]:
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        return []
    return _walk_tree_max_depth(repo_root, max_depth)


def _snapshot_tmp_omnix(tmp_root: Path, max_depth_under: int = 2) -> list[tuple[str, int, int]]:
    tmp_root = tmp_root.resolve()
    out: list[tuple[str, int, int]] = []
    if not tmp_root.is_dir():
        return out
    try:
        with os.scandir(tmp_root) as it:
            for ent in it:
                if not ent.name.startswith("omnix_"):
                    continue
                p = Path(ent.path)
                trip = _stat_triple(p)
                if trip:
                    out.append(trip)
                if ent.is_dir(follow_symlinks=False):
                    out.extend(_walk_tree_max_depth(p, max_depth_under))
    except OSError as e:
        _LOG.debug("tmp snapshot failed: %s", e)
    return out


@dataclass(frozen=True)
class SandboxConfig:
    repo_root: Path
    omnix_dir: Path
    hypothesis_dir: Path
    verify_workspace_dir: Path
    strict_repo_snapshot: bool = False
    tmp_root: Path | None = None

    def resolved_tmp_root(self) -> Path:
        return (self.tmp_root or Path(os.environ.get("OMNIX_FS_HYGIENE_TMP_ROOT", "/tmp"))).resolve()


def snapshot(config: SandboxConfig) -> frozenset[tuple[str, int, int]]:
    """Inventory (abs path, size, mtime_ns) for repo + tmp omnix_* regions."""
    repo_max: int | None
    if config.strict_repo_snapshot:
        repo_max = None
    else:
        repo_max = 3
    repo_entries = _snapshot_repo_region(config.repo_root.resolve(), repo_max)
    tmp_entries = _snapshot_tmp_omnix(config.resolved_tmp_root(), max_depth_under=2)
    merged: list[tuple[str, int, int]] = repo_entries + tmp_entries
    return frozenset(merged)


def diff_snapshots(
    before: frozenset[tuple[str, int, int]],
    after: frozenset[tuple[str, int, int]],
) -> list[str]:
    before_paths = {t[0] for t in before}
    return sorted({t[0] for t in after if t[0] not in before_paths})


def build_sandbox_roots(
    repo_root: Path,
    hypothesis_dir: Path,
    verify_workspace_dir: Path,
    extras: Sequence[Path] | None = None,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    rr = repo_root.resolve()
    od = (rr / ".omnix").resolve()
    for p in (
        hypothesis_dir.resolve(),
        verify_workspace_dir.resolve(),
        od,
    ):
        try:
            pr = p.resolve()
            if pr.is_dir() or pr.is_file():
                roots.append(pr)
        except OSError:
            continue
    if extras:
        for e in extras:
            try:
                roots.append(e.resolve())
            except OSError:
                continue
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        k = str(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return tuple(out)


def path_allowed_under_roots(abs_path: Path, roots: Sequence[Path]) -> bool:
    """True if abs_path resolves under any allowed root."""
    try:
        p = abs_path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            p.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def severity_for_path(abs_path: Path, repo_root: Path, tmp_root: Path) -> str:
    """HIGH / MEDIUM / LOW for an offending absolute path."""
    try:
        p = abs_path.resolve()
        rr = repo_root.resolve()
        rel = p.relative_to(rr)
        depth = len(rel.parts)
        if depth == 1:
            return "HIGH"
        if depth in (2, 3):
            return "MEDIUM"
        if depth > 3:
            return "MEDIUM"
    except ValueError:
        pass
    try:
        p = abs_path.resolve()
        tr = tmp_root.resolve()
        p.relative_to(tr)
        name = p.relative_to(tr).parts[0] if p != tr else ""
        if isinstance(name, str) and name.startswith("omnix_"):
            return "LOW"
        return "LOW"
    except ValueError:
        pass
    return "HIGH"


def hygiene_severity_score(label: str) -> int:
    return {"HIGH": 18, "MEDIUM": 12, "LOW": 6}.get(label.upper(), 10)


@dataclass(frozen=True)
class HygieneFinding:
    dimension: str
    severity: str
    target_function: str
    offending_paths: list[dict[str, Any]]
    sandbox_dirs: list[str]
    fuzz_inputs: str
    reproduction: str

    def as_finding_dict(self) -> dict[str, Any]:
        return {
            "kind": "filesystem_hygiene",
            "dimension": self.dimension,
            "severity": self.severity,
            "severity_score": hygiene_severity_score(self.severity),
            "target_function": self.target_function,
            "offending_paths": list(self.offending_paths),
            "sandbox_dirs": list(self.sandbox_dirs),
            "fuzz_inputs": self.fuzz_inputs,
            "reproduction": self.reproduction,
        }


def compute_finding(
    *,
    created_abs_paths: Sequence[str],
    path_sizes: dict[str, int],
    sandbox_roots: Sequence[Path],
    repo_root: Path,
    tmp_root: Path | None = None,
    target_function: str,
    fuzz_inputs: str,
    reproduction: str,
) -> HygieneFinding | None:
    """Emit one aggregated finding for paths outside sandbox_roots (P19: empty roots deny-all)."""
    tr = (tmp_root or Path("/tmp")).resolve()
    offenders: list[tuple[str, int, str]] = []
    for ps in created_abs_paths:
        p = Path(ps)
        if path_allowed_under_roots(p, sandbox_roots):
            continue
        sz = int(path_sizes.get(ps, 0))
        sev = severity_for_path(p, repo_root.resolve(), tr)
        offenders.append((ps, sz, sev))
    if not offenders:
        return None
    max_sev = "LOW"
    for _, _, s in offenders:
        if s == "HIGH":
            max_sev = "HIGH"
            break
        if s == "MEDIUM" and max_sev != "HIGH":
            max_sev = "MEDIUM"
    opaths = [{"path": x[0], "size": x[1]} for x in offenders]
    return HygieneFinding(
        dimension="filesystem_hygiene",
        severity=max_sev,
        target_function=target_function,
        offending_paths=opaths,
        sandbox_dirs=[str(r) for r in sandbox_roots],
        fuzz_inputs=fuzz_inputs,
        reproduction=reproduction,
    )


def merge_hygiene_into_result_entry(
    finding_dict: dict[str, Any],
    *,
    file_relp: str,
    function_name: str,
    lineno: int,
) -> dict[str, Any]:
    """Attach UI-facing file/function/lineno for studio ranking."""
    out = dict(finding_dict)
    out["file"] = file_relp
    out["function"] = function_name
    out["lineno"] = lineno
    out.setdefault(
        "reason",
        "Filesystem hygiene: writes detected outside the declared PBT sandbox.",
    )
    return out


def parse_bool_env(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key) or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return default


def hygiene_enabled() -> bool:
    return parse_bool_env("OMNIX_FS_HYGIENE_ENABLED", False)


def strict_hygiene() -> bool:
    return parse_bool_env("OMNIX_FS_HYGIENE_STRICT", False)


def load_sandbox_config_from_env() -> SandboxConfig | None:
    """Build SandboxConfig from env; returns None → detector inactive."""
    if not hygiene_enabled():
        return None
    rr = (os.environ.get("OMNIX_FS_HYGIENE_REPO_ROOT") or "").strip()
    hyp = (os.environ.get("OMNIX_FS_HYGIENE_HYPOTHESIS_DIR") or "").strip()
    vws = (os.environ.get("OMNIX_FS_HYGIENE_VERIFY_WS") or "").strip()
    if not rr or not hyp or not vws:
        _LOG.warning(
            "filesystem_hygiene: missing OMNIX_FS_HYGIENE_REPO_ROOT/"
            "HYPOTHESIS_DIR/VERIFY_WS — using deny-default roots (P19)"
        )
        try:
            repo_p = Path(rr or os.getcwd()).resolve()
        except OSError:
            repo_p = Path(".").resolve()
        try:
            hyp_p = Path(hyp).resolve() if hyp else (repo_p / ".omnix" / "hypothesis")
        except OSError:
            hyp_p = repo_p / ".omnix" / "hypothesis"
        try:
            vws_p = Path(vws).resolve() if vws else (repo_p / ".omnix" / "verify_workspace")
        except OSError:
            vws_p = repo_p / ".omnix" / "verify_workspace"
        return SandboxConfig(
            repo_root=repo_p,
            omnix_dir=(repo_p / ".omnix").resolve(),
            hypothesis_dir=hyp_p,
            verify_workspace_dir=vws_p,
            strict_repo_snapshot=strict_hygiene(),
        )
    repo_p = Path(rr).resolve()
    hyp_p = Path(hyp).resolve()
    vws_p = Path(vws).resolve()
    tmp_raw = (os.environ.get("OMNIX_FS_HYGIENE_TMP_ROOT") or "").strip()
    tmp_p = Path(tmp_raw).resolve() if tmp_raw else None
    return SandboxConfig(
        repo_root=repo_p,
        omnix_dir=(repo_p / ".omnix").resolve(),
        hypothesis_dir=hyp_p,
        verify_workspace_dir=vws_p,
        strict_repo_snapshot=strict_hygiene(),
        tmp_root=tmp_p,
    )


def validated_sandbox_roots(cfg: SandboxConfig) -> tuple[Path, ...]:
    """Resolve sandbox roots; reject paths with ``..`` segments before resolve."""
    extras_raw = (os.environ.get("OMNIX_FS_HYGIENE_EXTRA_ROOTS") or "").strip()
    extras: list[Path] = []
    if extras_raw:
        for part in extras_raw.split(os.pathsep):
            p = Path(part.strip())
            if not part.strip():
                continue
            if ".." in p.parts:
                _LOG.warning("filesystem_hygiene: ignoring unsafe extra root %s", part)
                continue
            try:
                extras.append(p.resolve())
            except OSError:
                continue
    return build_sandbox_roots(
        cfg.repo_root,
        cfg.hypothesis_dir,
        cfg.verify_workspace_dir,
        extras=extras,
    )
