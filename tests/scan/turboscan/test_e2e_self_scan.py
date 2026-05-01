"""R8/R9/R11 — optional full OMNIX self-scan (set OMNIX_TURBOSCAN_E2E=1)."""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("hypothesis")

from find_bugs.runner import run_find_bugs  # noqa: E402
from scan.turboscan.orchestrator import scan  # noqa: E402


@pytest.mark.skipif(
    os.environ.get("OMNIX_TURBOSCAN_E2E", "").lower() not in ("1", "true", "yes"),
    reason="Set OMNIX_TURBOSCAN_E2E=1 to run full-repo timing gates",
)
def test_R8_full_self_scan_under_30s_on_omnix(omnix_repo_path):
    t0 = time.monotonic()
    result = scan(omnix_repo_path, mode="full", workers=8, examples_default=100)
    elapsed = time.monotonic() - t0
    assert elapsed < 30.0, f"TURBOSCAN took {elapsed:.1f}s — exceeds 30s budget"
    assert result.scan_completed_successfully
    print(f"\n[R8 PASSED] TURBOSCAN full self-scan: {elapsed:.2f}s")


@pytest.mark.skipif(
    os.environ.get("OMNIX_TURBOSCAN_E2E", "").lower() not in ("1", "true", "yes"),
    reason="Set OMNIX_TURBOSCAN_E2E=1",
)
def test_R9_turboscan_finds_at_least_as_many_bugs_as_legacy(omnix_repo_path):
    _, _, legacy_detail = run_find_bugs(
        str(omnix_repo_path),
        examples=50,
        json_mode=True,
        no_bundle=True,
        turboscan=False,
    )
    turbo = scan(omnix_repo_path, mode="full", examples_default=100)
    assert legacy_detail is not None
    legacy_rows = legacy_detail.get("findings") or []
    legacy_bugs = {
        (str(b.get("function")), finding_bug_class(b))
        for b in legacy_rows
        if isinstance(b, dict)
    }
    turbo_bugs = {(f.function_name, f.bug_class) for f in turbo.findings}
    missed = legacy_bugs - turbo_bugs
    assert not missed, f"TURBOSCAN missed bugs vs legacy: {sorted(missed)[:10]}"


def finding_bug_class(row: dict) -> str:
    dim = str(row.get("dimension") or "")
    if dim == "filesystem_hygiene":
        return "filesystem_hygiene"
    return str(row.get("kind") or "pbt_failure")
