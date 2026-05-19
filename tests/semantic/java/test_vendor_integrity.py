"""Supply-chain integrity gate for the vendored JavaParser stack.

Re-hashes every JAR under `src/omnix/semantic/java/vendor/` and asserts the
hash matches `SHA256SUMS`. A JAR byte change without a `SHA256SUMS` update
fails CI loudly — preventing silent supply-chain drift.

Also asserts:
  - `VENDOR.md` is present and contains Apache 2.0 attribution.
  - Exactly the expected JAR set is vendored (no orphan downloads, no
    accidental second-version checkin).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

_VENDOR_DIR: Path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "omnix"
    / "semantic"
    / "java"
    / "vendor"
)

# Pinned set of vendored JARs. Bumping versions = single-concern slice
# that updates this constant + SHA256SUMS + the build script in lockstep.
_EXPECTED_JARS: frozenset[str] = frozenset(
    {
        "javaparser-core-3.26.3.jar",
        "javaparser-symbol-solver-core-3.26.3.jar",
        "javassist-3.30.2-GA.jar",
        "javaparser-emitter.jar",
        "java-equivalence-harness.jar",
        "equivalence-probe-runner.jar",
    }
)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_sha256sums() -> dict[str, str]:
    sums_path = _VENDOR_DIR / "SHA256SUMS"
    out: dict[str, str] = {}
    for line in sums_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition(" ")
        out[name.strip().lstrip("*")] = digest.strip()
    return out


def test_sha256sums_file_present_and_non_empty() -> None:
    sums_path = _VENDOR_DIR / "SHA256SUMS"
    assert sums_path.exists(), f"missing: {sums_path}"
    entries = _load_sha256sums()
    assert entries, "SHA256SUMS parsed empty — file format drift?"


def test_exactly_expected_jar_set_vendored() -> None:
    """No orphan downloads, no accidental side-by-side versions."""
    actual = {p.name for p in _VENDOR_DIR.glob("*.jar")}
    assert actual == _EXPECTED_JARS, (
        f"vendored JAR set drift:\n"
        f"  expected: {sorted(_EXPECTED_JARS)}\n"
        f"  actual:   {sorted(actual)}\n"
        f"Bump = single-concern slice updating _EXPECTED_JARS + SHA256SUMS + build.sh."
    )


@pytest.mark.parametrize("jar_name", sorted(_EXPECTED_JARS))
def test_vendored_jar_matches_sha256sums(jar_name: str) -> None:
    """Hash gate — JAR byte change without SHA256SUMS update fails hard."""
    jar_path = _VENDOR_DIR / jar_name
    assert jar_path.exists(), f"vendored JAR missing: {jar_path}"

    declared = _load_sha256sums().get(jar_name)
    assert declared, f"SHA256SUMS has no entry for {jar_name}"

    actual = _sha256_of(jar_path)
    assert declared == actual, (
        f"SHA256 mismatch for {jar_name}:\n"
        f"  declared: {declared}\n"
        f"  actual:   {actual}\n"
        f"Either the JAR was tampered with or SHA256SUMS wasn't updated.\n"
        f"Rebuild via `bash src/omnix/semantic/java/jvm/build.sh` if intentional."
    )


def test_vendor_md_attests_apache_license() -> None:
    md = _VENDOR_DIR / "VENDOR.md"
    assert md.exists(), f"missing: {md}"
    content = md.read_text()
    assert "Apache License 2.0" in content, "VENDOR.md must attest Apache 2.0"
    assert "Maven Central" in content, "VENDOR.md must name the source"
    assert "3.26.3" in content, "VENDOR.md must pin the JavaParser version"
