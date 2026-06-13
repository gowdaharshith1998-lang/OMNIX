# Compliance: P17 (no mutable default args in AXIOM modules).
"""Emit per-finding Ed25519 receipts and ML-DSA-signed scan manifests (slice 18d)."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.receipts import keystore as mldsa_keystore
from omnix.receipts import sign as mldsa_sign
from omnix.receipts import verify as mldsa_verify
from omnix.receipts.finding_keys import (
    omnix_home,
    project_privkey_path,
    sign_bytes_mldsa,
    sign_finding,
    verify_bytes_mldsa,
    verify_finding,
)
from omnix.receipts.finding_receipt import (
    FindingReceipt,
    compute_finding_id,
    compute_project_id,
    now_iso8601_utc,
)
from omnix.receipts.merkle import compute_leaf_hash, compute_merkle_root

_LOG = logging.getLogger("omnix.find_bugs.receipt_emitter")


class MissingEd25519ProjectKeyError(Exception):
    """Project Ed25519 key missing (~/.omnix/keys/<project_id>.pem)."""


class MissingMldsaKeystoreError(Exception):
    def __init__(self, path: Path) -> None:
        self.path = path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def find_bugs_tool_version() -> str:
    """Git short SHA when available, else ``omnix_version``."""
    root = _repo_root()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    from omnix.omnix_version import __version__

    return str(__version__)


def scan_id_now() -> str:
    """ISO 8601 UTC (minute resolution, ``-`` in time) + 8-char hex nonce."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    nonce = secrets.token_hex(4)
    return f"{ts}_{nonce}"


def derive_code_snippet_hash(file_path: Path, line_start: int, line_end: int) -> str:
    """SHA-256 hex of inclusive line range (1-indexed), UTF-8 decoded lines joined."""
    if not file_path.is_file():
        return hashlib.sha256(b"<file_missing>").hexdigest()
    try:
        raw = file_path.read_bytes()
    except OSError:
        return hashlib.sha256(b"<file_unreadable>").hexdigest()
    lines = raw.splitlines(keepends=True)
    lo = max(1, line_start) - 1
    hi = max(lo, line_end)
    snippet = b"".join(lines[lo:hi])
    return hashlib.sha256(snippet).hexdigest()


def _severity_label(score: int, finding: dict[str, Any]) -> str:
    s = int(score)
    if finding.get("kind") == "memory_pathology" or s >= 90:
        return "critical"
    if s >= 40:
        return "high"
    if s >= 20:
        return "med"
    if s >= 8:
        return "low"
    return "info"


def _rule_base(f: dict[str, Any]) -> str:
    if f.get("kind") == "memory_pathology":
        return "find_bugs.memory_pathology"
    if str(f.get("dimension") or "") == "filesystem_hygiene":
        return "find_bugs.filesystem_hygiene"
    ru = f.get("runner_used")
    if ru:
        return f"find_bugs.layer6.{ru}"
    k = f.get("kind")
    if k:
        return f"find_bugs.{k}"
    return "find_bugs.pbt_failure"


def derive_rule_id(f: dict[str, Any]) -> str:
    """Stable rule string; includes function name so ``finding_id`` stays unique."""
    fn = str(f.get("function") or "")
    return f"{_rule_base(f)}#{fn}"


def _summarize_finding(f: dict[str, Any]) -> str:
    if f.get("reason"):
        return str(f["reason"])[:200]
    failures = f.get("failures") or []
    if isinstance(failures, list) and failures and isinstance(failures[0], dict):
        x = failures[0]
        msg = str(x.get("message") or x.get("exception_message") or "")[:180]
        et = str(x.get("exception_type") or "Finding")
        out = f"{et}: {msg}".strip()
        return out[:200] if out else f"{f.get('function','?')} finding"
    return f"{f.get('function', '?')}:{f.get('file', '?')}"[:200]


def _model_for_finding(f: dict[str, Any]) -> str:
    ru = f.get("runner_used")
    if ru:
        return str(ru)
    meta = f.get("metadata")
    if isinstance(meta, dict):
        m = meta.get("model")
        if m:
            return str(m)
    return "static"


def _prompt_response_hashes(f: dict[str, Any]) -> tuple[str | None, str | None]:
    """Layer6 / Fabric may stash transcripts under metadata (optional)."""
    meta = f.get("metadata")
    if not isinstance(meta, dict):
        return None, None
    for key_p, key_r in (
        ("llm_prompt", "llm_response"),
        ("prompt", "response"),
        ("layer6_prompt", "layer6_response"),
    ):
        p = meta.get(key_p)
        r = meta.get(key_r)
        if isinstance(p, str) and p.strip():
            ph = hashlib.sha256(p.encode("utf-8")).hexdigest()
            rh = (
                hashlib.sha256(r.encode("utf-8")).hexdigest()
                if isinstance(r, str) and r.strip()
                else None
            )
            return ph, rh
    return None, None


def finding_dict_to_receipt(
    finding: dict[str, Any],
    project_id: str,
    project_root: Path,
    timestamp: str,
    omnix_version: str,
) -> FindingReceipt:
    root = project_root.resolve(strict=True)
    rel = str(finding.get("file") or "").replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("finding missing relative file path")
    line_start = max(1, int(finding.get("lineno") or 1))
    line_end = max(line_start, line_start)
    rule = derive_rule_id(finding)
    fid = compute_finding_id(project_id, rel, line_start, rule)
    snippet_path = root / rel
    snippet_hash = derive_code_snippet_hash(snippet_path, line_start, line_end)
    score = int(finding.get("severity_score") or 0)
    sev = _severity_label(score, finding)
    prompt_h, response_h = _prompt_response_hashes(finding)
    return FindingReceipt(
        finding_id=fid,
        project_id=project_id,
        file=rel,
        line_start=line_start,
        line_end=line_end,
        severity=sev,
        rule=rule,
        model=_model_for_finding(finding),
        prompt_hash=prompt_h,
        response_hash=response_h,
        finding_summary=_summarize_finding(finding),
        code_snippet_hash=snippet_hash,
        timestamp=timestamp,
        omnix_version=omnix_version,
    )


def _global_mldsa_secret_path() -> Path:
    return omnix_home() / ".omnix" / "keys" / "secret.pem"


def emit_scan_receipts(
    findings: list[dict[str, Any]],
    project_root: Path,
    *,
    scan_started_at: str,
    scan_finished_at: str | None = None,
    files_scanned: int,
    receipts_home: Path | None = None,
) -> Path:
    """Write per-finding receipts + signed manifest. Returns scan directory path."""
    root = project_root.resolve(strict=True)
    project_id = compute_project_id(root)
    ed25519_priv = project_privkey_path(project_id)
    if not ed25519_priv.is_file():
        raise MissingEd25519ProjectKeyError()
    mldsa_secret = _global_mldsa_secret_path()
    if not mldsa_secret.is_file():
        raise MissingMldsaKeystoreError(mldsa_secret.resolve())

    finished = scan_finished_at or now_iso8601_utc()
    from omnix.omnix_version import __version__ as ov

    omnix_version = str(ov)

    receipts_base = receipts_home if receipts_home is not None else omnix_home()
    sid = scan_id_now()
    scan_dir = receipts_base / ".omnix" / "receipts" / "findings" / project_id / sid
    scan_dir.mkdir(parents=True, exist_ok=True)

    timestamp_shared = finished
    receipts_sorted: list[FindingReceipt] = []
    for fd in findings:
        receipts_sorted.append(
            finding_dict_to_receipt(fd, project_id, root, timestamp_shared, omnix_version)
        )
    receipts_sorted.sort(key=lambda r: r.finding_id)

    leaf_entries: list[dict[str, str]] = []
    leaf_digests: list[bytes] = []

    for r in receipts_sorted:
        canonical = r.canonical_json()
        leaf_b = compute_leaf_hash(canonical)
        leaf_entries.append({"finding_id": r.finding_id, "leaf_hash": leaf_b.hex()})
        leaf_digests.append(leaf_b)
        json_path = scan_dir / f"{r.finding_id}.json"
        sig_path = scan_dir / f"{r.finding_id}.sig"
        json_path.write_bytes(canonical)
        sig_b64 = sign_finding(asdict(r), project_id)
        sig_path.write_text(sig_b64 + "\n", encoding="ascii")
        # Hybrid signing: also emit a post-quantum ML-DSA-65 signature over the
        # same canonical bytes, so every per-finding receipt is directly PQC
        # signed (not only Merkle-anchored under the ML-DSA manifest).
        (scan_dir / f"{r.finding_id}.mldsa.sig").write_text(
            sign_bytes_mldsa(canonical), encoding="ascii"
        )

    root_hex = compute_merkle_root(leaf_digests)

    by_severity: dict[str, int] = {
        "info": 0,
        "low": 0,
        "med": 0,
        "high": 0,
        "critical": 0,
    }
    by_rule: dict[str, int] = {}
    for r in receipts_sorted:
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
        by_rule[r.rule] = by_rule.get(r.rule, 0) + 1

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "manifest_kind": "omnix_scan_manifest",
        "scan_id": sid,
        "project_id": project_id,
        "scan_root": root.as_posix(),
        "scan_started_at": scan_started_at,
        "scan_finished_at": finished,
        "omnix_version": omnix_version,
        "tool_version": {"find_bugs": find_bugs_tool_version()},
        "finding_count": len(receipts_sorted),
        "merkle_root": root_hex,
        "finding_leaves": leaf_entries,
        "scan_summary": {
            "by_severity": by_severity,
            "by_rule": dict(sorted(by_rule.items(), key=lambda kv: kv[0])),
            "files_scanned": int(files_scanned),
        },
    }

    manifest_bytes = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    from omnix.receipts.secure_keyfile import read_secret as _read_secret

    sk_pem = _read_secret(mldsa_secret)
    sk = mldsa_keystore.secret_from_pem(sk_pem)
    rnd = secrets.token_bytes(32)
    sig_raw = mldsa_sign.sign_bytes(sk, manifest_bytes, b"", rnd)
    sig_pem = mldsa_keystore.signature_to_pem(sig_raw)

    (scan_dir / "scan_manifest.json").write_bytes(manifest_bytes)
    (scan_dir / "scan_manifest.sig").write_text(sig_pem, encoding="ascii")

    _LOG.info("Emitted scan receipts under %s", scan_dir)
    return scan_dir


def verify_scan_directory(
    scan_dir: Path,
    ed25519_pubkey: Path,
    mldsa_pubkey: Path,
) -> tuple[bool, str]:
    """Verify scan artifacts (tests + future step 3). Returns ``(ok, reason)``."""
    manifest_path = scan_dir / "scan_manifest.json"
    sig_path = scan_dir / "scan_manifest.sig"
    if not manifest_path.is_file():
        return False, "missing_manifest"
    if not sig_path.is_file():
        return False, "missing_signature"

    manifest_bytes = manifest_path.read_bytes()
    try:
        sig_pem = sig_path.read_text(encoding="ascii")
        pk = mldsa_keystore.public_from_pem(mldsa_pubkey.read_text(encoding="ascii"))
        sig_raw = mldsa_keystore.signature_from_pem(sig_pem)
    except (OSError, ValueError):
        return False, "invalid_manifest_signature"

    if not mldsa_verify.verify_bytes(pk, manifest_bytes, b"", sig_raw):
        return False, "invalid_manifest_signature"

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, "invalid_manifest_signature"

    leaf_entries = manifest.get("finding_leaves")
    if not isinstance(leaf_entries, list):
        return False, "merkle_mismatch"

    leaves_recomputed: list[bytes] = []
    for entry in leaf_entries:
        if not isinstance(entry, dict):
            return False, "merkle_mismatch"
        fid = str(entry.get("finding_id") or "")
        expected_hex = str(entry.get("leaf_hash") or "")
        json_p = scan_dir / f"{fid}.json"
        sig_p = scan_dir / f"{fid}.sig"
        if not json_p.is_file() or not sig_p.is_file():
            return False, "missing_finding"
        canonical = json_p.read_bytes()
        leaf_b = compute_leaf_hash(canonical)
        if leaf_b.hex() != expected_hex:
            return False, "merkle_mismatch"
        try:
            receipt_obj = json.loads(canonical.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, "merkle_mismatch"
        sig_str = sig_p.read_text(encoding="ascii").strip()
        try:
            if not verify_finding(receipt_obj, sig_str, ed25519_pubkey):
                return False, "finding_signature_invalid"
        except (FileNotFoundError, OSError, ValueError):
            return False, "finding_signature_invalid"
        # Post-quantum signature: required when present (always, for receipts
        # emitted by current OMNIX); absent only on legacy scan dirs, which
        # still hold via Ed25519 + the ML-DSA-signed Merkle root.
        mldsa_sig_p = scan_dir / f"{fid}.mldsa.sig"
        if mldsa_sig_p.is_file():
            if not verify_bytes_mldsa(
                canonical, mldsa_sig_p.read_text(encoding="ascii"), mldsa_pubkey
            ):
                return False, "finding_pqc_signature_invalid"
        leaves_recomputed.append(leaf_b)

    expected_root = str(manifest.get("merkle_root") or "")
    if compute_merkle_root(leaves_recomputed) != expected_root:
        return False, "merkle_mismatch"

    return True, "ok"
