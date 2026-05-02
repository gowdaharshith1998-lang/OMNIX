# Slice 18d — Compliance Vault Foundation

**Tag**: `v0.5-compliance-vault-foundation`  
**Shipped**: 2026-05-02 → 2026-05-03 (steps 1–3 + 3.1)  
**Test counts at close**: 435+ Python passed, 5 skipped + 170 frontend passing  
**Version bump**: 0.1.0 → 0.5.0

## TL;DR

Slice 18d adds audit-grade, tamper-evident evidence for AI-assisted static analysis: each finding is signed, and each scan is anchored by a post-quantum manifest over a Merkle tree of finding hashes. Operators get **`omnix axiom` verify/export commands**, **localhost read-only APIs**, and a **Finding Scans** tab in Studio’s Receipts drawer. The architectural bet is **hybrid signing** — fast Ed25519 per finding plus ML-DSA-65 on the scan manifest — so scale and long-horizon auditability coexist.

## Hybrid signing model

Two layers, two algorithms, bound by a Merkle tree over per-finding hashes.

| Layer | Algorithm | Key material | Cost |
|-------|-----------|----------------|------|
| Per-finding receipt | Ed25519 (64-byte sigs) | `~/.omnix/keys/<project_id>.pem` (private); `.omnix/pubkey.pem` in project | ~1ms × N findings |
| Scan manifest | ML-DSA-65 (post-quantum) | `~/.omnix/keys/secret.pem` / `public.pem` (AXIOM keystore) | ~50–200ms × 1 |

The manifest signature anchors the whole scan. Per-finding signatures are cheap and individually verifiable; integrity against deletion or reordering is enforced by recomputing the Merkle root from on-disk receipts and comparing to the manifest. Tampering breaks the root or the ML-DSA signature — forging both is intended to be infeasible even against quantum-capable adversaries at the manifest layer.

## What shipped

### Step 1 — Receipt foundation

`FindingReceipt` + canonical JSON (sorted keys, compact separators, UTF-8), **schema_version `1.0`**, Ed25519 project keys, `compute_project_id()`, `sign_finding` / `verify_finding`, **`omnix axiom keygen`** (idempotent).

### Step 2 — Emission + Merkle manifest

`src/axiom/merkle.py` (RFC 6962-style), `receipt_emitter.emit_scan_receipts` + `verify_scan_directory`, **`omnix find-bugs … --emit-receipts`** (opt-in). Tests cover modify-finding / delete-finding / manifest tampering.

### Step 3 — Verify CLI + API + Studio

**CLI**: `verify-finding`, `verify-scan`, `export-vault`. **API**: `GET /api/findings/scans`, `POST /api/findings/verify-scan` (localhost-only; `scan_id` validated with `^[A-Za-z0-9._:-]{20,80}$`; path traversal rejected). **Studio**: Receipts drawer **Finding Scans** tab + per-row Verify.

### Step 3.1 — Pip-entry wiring

`sys.path` bootstrap at top of `src/cli.py` so pip-installed `omnix` resolves `from src.*`; **`find-bugs`** registered on the Click group. Smoke tests guard the pip-entry path.

## API surface

| Route | Method | Notes |
|-------|--------|--------|
| `GET /api/findings/scans` | GET | `{ scans: [{ scan_id, scan_started_at, scan_finished_at, finding_count, dir_path_relative, manifest_kind }, …] }` sorted by `scan_started_at` DESC |
| `POST /api/findings/verify-scan` | POST `{ scan_id }` | `{ verified, reason, scan_id, finding_count, manifest_summary }`; read-only verification |

Non-localhost → **403**. Bad `scan_id` / traversal → **400**; missing scan → **404**.

## CLI surface

| Command | Role |
|---------|------|
| `omnix axiom keygen [--project PATH]` | Ensure Ed25519 keypair for project |
| `omnix axiom verify-finding <receipt.json> …` | Verify one receipt |
| `omnix axiom verify-scan <scan_dir> …` | Verify directory (receipts + manifest + sigs) |
| `omnix axiom export-vault <project_path> …` | Auditor handoff zip |
| `omnix find-bugs <path> [--emit-receipts]` | Scan; emit vault when flag set |

## Vault layout

```
~/.omnix/keys/<project_id>.pem                              # Ed25519 private (0600)
<project_root>/.omnix/pubkey.pem                            # Ed25519 public
~/.omnix/keys/secret.pem                                    # ML-DSA private
~/.omnix/keys/public.pem                                    # ML-DSA public
~/.omnix/receipts/findings/<project_id>/<scan_id>/
    <finding_id>.json
    <finding_id>.sig
    scan_manifest.json
    scan_manifest.sig
```

## Schema lock — `schema_version: "1.0"`

Finding receipt and scan manifest **v1.0** are treated as a **one-way door**: additive fields may bump minor; removing or renaming fields is breaking (major) and invalidates historical receipts. Plan migrations accordingly.

## Architecture decisions

- **Hybrid Ed25519 + ML-DSA** — speed at emission volume; PQ anchor where auditors concentrate.
- **Single project key** — multi-environment keys deferred until a design partner requires it (target v0.6+).
- **Two-level receipts + manifest** — per-finding provenance plus scan-wide integrity (incl. deletion awareness via Merkle roster).
- **`--emit-receipts` opt-in** — no default filesystem side effects for existing `find-bugs` users.
- **Findings API localhost-only** — external verification via CLI / exported zip; avoids auth on this slice.
- **Pip `sys.path` bootstrap** — systemic fix for `from src.*` under entry-point installs.

## What we learned

- Locking **schema_version 1.0** early avoided churn on field names and serialization.
- **pytest-from-repo-root ≠ pip-installed CLI**; smoke the real entry point before calling a step “done.”
- **Merkle + manifest** closes gaps that pure per-finding signatures leave for roster tampering.

## What’s deferred

- **Slice 18e** — Rust hot path / TURBOSCAN — **customer-pulled only**.
- **Slice 19** — Agentic Trust Layer (MCP) — gated on product signals (e.g. SWE-bench trajectory), not started here.
- **Slice 20** — Calibra / confidence fields in receipts — after stable v0.5+.
- **v0.6+** — standalone verifier (no full OMNIX install), per-environment keys, rotation UX.

## Next

**Design-partner outreach** — Compliance Vault is the artifact for enterprise conversations; engineering pauses for net-new surface until a pilot LOI or a pulled requirement appears.
