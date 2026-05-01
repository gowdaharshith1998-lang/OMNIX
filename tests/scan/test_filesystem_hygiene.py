"""Slice 17b — filesystem hygiene detector (EARS acceptance tests)."""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import pytest

from scan.filesystem_hygiene import (
    HygieneFinding,
    SandboxConfig,
    build_sandbox_roots,
    compute_finding,
    diff_snapshots,
    hygiene_severity_score,
    severity_for_path,
    snapshot,
)

pytestmark = pytest.mark.usefixtures("tmp_path")


def test_R1_snapshot_captures_depth3_inventory(tmp_path: Path) -> None:
    """R1: snapshot captures path + size + mtime at depth ≤3."""
    repo = tmp_path / "repo"
    (repo / "a" / "b").mkdir(parents=True)
    f = repo / "a" / "b" / "f.txt"
    f.write_text("hi", encoding="utf-8")
    (repo / "a" / "b" / "deepdir").mkdir()
    (repo / "a" / "b" / "deepdir" / "too_deep.txt").write_text("x", encoding="utf-8")
    hyp = repo / ".omnix" / "hypothesis"
    hyp.mkdir(parents=True)
    cfg = SandboxConfig(
        repo_root=repo.resolve(),
        omnix_dir=(repo / ".omnix").resolve(),
        hypothesis_dir=hyp.resolve(),
        verify_workspace_dir=(repo / ".omnix" / "verify_workspace").resolve(),
        strict_repo_snapshot=False,
    )
    inv = snapshot(cfg)
    keys = {t[0] for t in inv}
    assert any(str(f.resolve()) == k for k in keys)
    deep = repo / "a" / "b" / "deepdir" / "too_deep.txt"
    assert not any(str(deep.resolve()) == k for k in keys)


def test_R2_resnapshot_diff_fires_on_pbt_case_completion(tmp_path: Path) -> None:
    """R2: snap → write file → snap → diff returns the new file."""
    repo = tmp_path / "r"
    repo.mkdir()
    hyp = repo / ".omnix" / "hypothesis"
    vws = repo / ".omnix" / "verify_workspace"
    hyp.mkdir(parents=True)
    vws.mkdir(parents=True)
    cfg = SandboxConfig(
        repo_root=repo.resolve(),
        omnix_dir=(repo / ".omnix").resolve(),
        hypothesis_dir=hyp.resolve(),
        verify_workspace_dir=vws.resolve(),
        strict_repo_snapshot=False,
    )
    before = snapshot(cfg)
    nf = repo / "new_file.txt"
    nf.write_text("x", encoding="utf-8")
    after = snapshot(cfg)
    created = diff_snapshots(before, after)
    assert str(nf.resolve()) in created


def test_R3_finding_emitted_for_outofsandbox_path(tmp_path: Path) -> None:
    """R3: file created outside sandbox triggers finding with all 7 fields."""
    repo = tmp_path / "repo"
    repo.mkdir()
    hyp = repo / ".omnix" / "hypothesis"
    vws = repo / ".omnix" / "verify_workspace"
    hyp.mkdir(parents=True)
    vws.mkdir(parents=True)
    leak = repo / "BAD"
    leak.mkdir()
    roots = build_sandbox_roots(
        repo.resolve(),
        hyp.resolve(),
        vws.resolve(),
    )
    finding = compute_finding(
        created_abs_paths=[str(leak.resolve())],
        path_sizes={str(leak.resolve()): 0},
        sandbox_roots=roots,
        repo_root=repo.resolve(),
        target_function="fixture.mod:leaky",
        fuzz_inputs="('..',)",
        reproduction="PYTHONPATH=src python -m verify.cli …",
    )
    assert finding is not None
    assert isinstance(finding, HygieneFinding)
    assert finding.dimension == "filesystem_hygiene"
    assert finding.severity in ("HIGH", "MEDIUM", "LOW")
    assert finding.target_function == "fixture.mod:leaky"
    assert finding.offending_paths and finding.offending_paths[0]["path"]
    assert finding.sandbox_dirs
    assert finding.fuzz_inputs
    assert finding.reproduction
    d = finding.as_finding_dict()
    assert d["dimension"] == "filesystem_hygiene"
    assert "severity_score" in d


def test_R3_severity_HIGH_when_path_at_repo_root(tmp_path: Path) -> None:
    """R3: severity = HIGH when path lives at depth 1 of repo root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    child = repo / "garbage"
    assert severity_for_path(child.resolve(), repo.resolve(), Path("/tmp")) == "HIGH"


def test_R3_severity_MEDIUM_when_path_nested_in_repo(tmp_path: Path) -> None:
    """R3: severity = MEDIUM when path is depth 2-3 in repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    p2 = repo / "x" / "y"
    assert severity_for_path(p2.resolve(), repo.resolve(), Path("/tmp")) == "MEDIUM"
    p3 = repo / "x" / "y" / "z"
    assert severity_for_path(p3.resolve(), repo.resolve(), Path("/tmp")) == "MEDIUM"


def test_R3_severity_LOW_when_path_in_tmp_but_not_omnix_prefix(tmp_path: Path) -> None:
    """R3: severity = LOW when path is in /tmp/foo not /tmp/omnix_*."""
    repo = tmp_path / "repo"
    repo.mkdir()
    tdir = tmp_path / "tmp_stub"
    tdir.mkdir()
    p = tdir / "not_omnix" / "x"
    p.parent.mkdir(parents=True)
    assert severity_for_path(p.resolve(), repo.resolve(), tdir.resolve()) == "LOW"


def test_R6_overhead_under_25ms_median_for_500_files(tmp_path: Path) -> None:
    """R6: median snapshot+diff overhead < 25ms on 500-file workspace."""
    repo = tmp_path / "repo"
    hyp = repo / ".omnix" / "hypothesis"
    vws = repo / ".omnix" / "verify_workspace"
    for i in range(500):
        d = repo / "l1" / "l2"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"f{i}.txt").write_text("z", encoding="utf-8")
    hyp.mkdir(parents=True)
    vws.mkdir(parents=True)
    cfg = SandboxConfig(
        repo_root=repo.resolve(),
        omnix_dir=(repo / ".omnix").resolve(),
        hypothesis_dir=hyp.resolve(),
        verify_workspace_dir=vws.resolve(),
        strict_repo_snapshot=False,
    )
    timings_ms: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter_ns()
        a = snapshot(cfg)
        b = snapshot(cfg)
        _ = diff_snapshots(a, b)
        timings_ms.append((time.perf_counter_ns() - t0) / 1e6)
    med = statistics.median(timings_ms)
    p99 = sorted(timings_ms)[98] if len(timings_ms) >= 99 else max(timings_ms)
    print(f"R6 median_ms={med:.3f} p99_ms={p99:.3f}")
    assert med < 25.0, f"median {med} >= 25ms"
    assert p99 < 100.0, f"p99 {p99} >= 100ms"


def test_R8_detector_state_never_leaks_into_findings(tmp_path: Path) -> None:
    """R8: in-memory snapshots only; hygiene scan of sandbox-only writes → no finding."""
    repo = tmp_path / "repo"
    hyp = repo / ".omnix" / "hypothesis"
    vws = repo / ".omnix" / "verify_workspace"
    hyp.mkdir(parents=True)
    vws.mkdir(parents=True)
    (vws / "only_here").write_text("ok", encoding="utf-8")
    cfg = SandboxConfig(
        repo_root=repo.resolve(),
        omnix_dir=(repo / ".omnix").resolve(),
        hypothesis_dir=hyp.resolve(),
        verify_workspace_dir=vws.resolve(),
        strict_repo_snapshot=False,
    )
    before = snapshot(cfg)
    (vws / "second").write_text("ok", encoding="utf-8")
    after = snapshot(cfg)
    created = diff_snapshots(before, after)
    roots = build_sandbox_roots(repo.resolve(), hyp.resolve(), vws.resolve())
    sizes = {str((vws / "second").resolve()): 2}
    finding = compute_finding(
        created_abs_paths=created,
        path_sizes=sizes,
        sandbox_roots=roots,
        repo_root=repo.resolve(),
        target_function="self.test",
        fuzz_inputs="()",
        reproduction="n/a",
    )
    assert finding is None


def test_R7_signal_helpers_score_mapping() -> None:
    assert hygiene_severity_score("HIGH") >= hygiene_severity_score("MEDIUM")
    assert hygiene_severity_score("MEDIUM") >= hygiene_severity_score("LOW")


def test_malformed_sandbox_config_fails_closed(tmp_path: Path) -> None:
    """P19: invalid sandbox roots → treat offenders as real leaks."""
    repo = tmp_path / "repo"
    repo.mkdir()
    roots = ()  # empty allow-list
    leak = repo / "x.txt"
    leak.write_text("a", encoding="utf-8")
    f = compute_finding(
        created_abs_paths=[str(leak.resolve())],
        path_sizes={str(leak.resolve()): 1},
        sandbox_roots=roots,
        repo_root=repo.resolve(),
        target_function="t:f",
        fuzz_inputs="()",
        reproduction="r",
    )
    assert f is not None


def test_tmp_snapshot_respects_omnix_prefix_only(tmp_path: Path) -> None:
    fake_tmp = tmp_path / "tmp"
    fake_tmp.mkdir()
    (fake_tmp / "other").mkdir()
    (fake_tmp / "omnix_test_scandir").mkdir()
    (fake_tmp / "omnix_test_scandir" / "nested").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    hyp = repo / ".omnix" / "hypothesis"
    vws = repo / ".omnix" / "verify_workspace"
    hyp.mkdir(parents=True)
    vws.mkdir(parents=True)
    cfg = SandboxConfig(
        repo_root=repo.resolve(),
        omnix_dir=(repo / ".omnix").resolve(),
        hypothesis_dir=hyp.resolve(),
        verify_workspace_dir=vws.resolve(),
        strict_repo_snapshot=False,
        tmp_root=fake_tmp.resolve(),
    )
    inv = snapshot(cfg)
    keys = {t[0] for t in inv}
    assert any("omnix_test_scandir" in k for k in keys)
    bad = str((fake_tmp / "other").resolve())
    assert bad not in keys
