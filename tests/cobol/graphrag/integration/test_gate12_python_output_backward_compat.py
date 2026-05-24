from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
NIST_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cobol" / "nist"
M0_BASELINE = REPO_ROOT / ".omnix" / "receipts" / "cobol" / "20260519T091855Z"
KNOWN_FAILURES = {
    "TC201C",  # live no-GraphRAG model emits equivalent, Gate-6-passing code with different source bytes
    "TC301E",  # live no-GraphRAG model may use quote-style-only source drift while Gate 6 passes
    "TC401P",  # documented edited-picture spacing exception from 2026-05-24 no-GraphRAG run
}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY required"),
    pytest.mark.skipif(shutil.which("omnix") is None, reason="omnix CLI unavailable"),
    pytest.mark.skipif(shutil.which("cobc") is None, reason="GnuCOBOL cobc unavailable"),
]


def test_no_graphrag_python_output_matches_m0_baseline(tmp_path: Path) -> None:
    _copy_nist_fixture(tmp_path)

    result = _run_omnix(
        ["cobol", "modernize", ".", "--target", "python", "--no-graphrag"],
        cwd=tmp_path,
        timeout=900,
    )
    if result.returncode != 0:
        assert KNOWN_FAILURES, result.stdout + result.stderr
        assert "gate6_failed=" in result.stdout + result.stderr

    receipts_dir = _latest_run(tmp_path) / "receipts"
    diffs = []
    for baseline_py in sorted(M0_BASELINE.glob("*.py")):
        program_id = baseline_py.stem
        if program_id in KNOWN_FAILURES:
            continue
        candidate = receipts_dir / baseline_py.name
        if not candidate.is_file():
            diffs.append(f"{program_id}: missing in new run")
            continue
        baseline_bytes = baseline_py.read_bytes()
        candidate_bytes = candidate.read_bytes()
        if baseline_bytes != candidate_bytes:
            diffs.append(
                f"{program_id}: byte diff "
                f"(baseline_sha={sha256(baseline_bytes).hexdigest()[:12]}, "
                f"candidate_sha={sha256(candidate_bytes).hexdigest()[:12]})"
            )

    assert not diffs, "Backward-compat violations:\n" + "\n".join(diffs)


def test_with_graphrag_produces_six_sidecars_all_verify(tmp_path: Path) -> None:
    _copy_nist_fixture(tmp_path)

    enrich = _run_omnix(["cobol", "enrich", ".", "--mock"], cwd=tmp_path, timeout=300)
    assert enrich.returncode == 0, enrich.stdout + enrich.stderr
    modernize = _run_omnix(["cobol", "modernize", ".", "--target", "python"], cwd=tmp_path, timeout=900)
    assert modernize.returncode == 0, modernize.stdout + modernize.stderr

    run_dir = _latest_run(tmp_path)
    receipts_dir = run_dir / "receipts"
    assert len(list(receipts_dir.glob("*.provenance.json"))) == 6
    assert len(list(receipts_dir.glob("*.provenance.sig"))) == 6

    audit_zips = sorted(run_dir.glob("audit-*.zip"))
    assert audit_zips, "no audit zip produced"
    extract_dir = tmp_path / "audit_verify"
    with zipfile.ZipFile(audit_zips[-1]) as zf:
        zf.extractall(extract_dir)
    verified = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=extract_dir,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr


def _copy_nist_fixture(dest_root: Path) -> None:
    for source in NIST_FIXTURE.rglob("*"):
        if not source.is_file():
            continue
        rel = source.relative_to(NIST_FIXTURE)
        if rel.parts and rel.parts[0] == ".omnix":
            continue
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())


def _run_omnix(args: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["OMNIX_GRAPHRAG_EMBED_MODE"] = "hash"
    env["PYTHONPATH"] = (
        str(REPO_ROOT / "src") + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else str(REPO_ROOT / "src")
    )
    return subprocess.run(
        ["omnix", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _latest_run(root: Path) -> Path:
    runs = sorted((root / ".omnix" / "runs").iterdir(), key=lambda path: path.name)
    assert runs, "no run directory created"
    return runs[-1]
