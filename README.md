# OMNIX

**OMNIX is, to our current knowledge, the only open-core code intelligence product that bundles universal Tree-Sitter parsing + self-evolving query patterns with ML-DSA-65 signed audit trail + hybrid universal PBT + sandbox-isolated auto-fix in one shipping repo.**

Point OMNIX at a codebase. Get an interactive 3D graph of every file, function, class, and connection.

## Quick Start

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

Browser opens. Explore your codebase in 3D.

Use `python omnix.py analyze /path --no-open` to start the React Studio server without launching a browser. Studio ingests into `<path>/.omnix/omnix.db`; the legacy `src/web/graph_data.json` export path is retired.

## Grammar Visibility (v0.4)

OMNIX exposes what the universal parser has learned: per-language profiles, pattern counts, recent grammar mutations, unknown file extensions, optional LLM call budget, and ML-DSA-signed evolution receipts (compliance-**aligned** design — not a certification).

### CLI

```bash
omnix grammar status
omnix grammar status --json
# Optional: --db /path/to/omnix.db  --grammar python
```

Sample table (from this repo after analyze):

```
Grammar     Files parsed  Avg quality  …  Active patterns  Recent mutations  Last evolution receipt
python      2844          0.755        …  10               7                 …/evolution_…_python.json
rust        14            0.750        …  1                0                 —
typescript  1597          0.610        …  18               4                 …/evolution_…_typescript.json
```

JSON mirrors API field names: `grammar_name`, `files_parsed`, `avg_quality`, `parse_modes`, `active_patterns`, `recent_mutations_30d`, `last_evolution_receipt`, plus `unknown_extensions`, `llm_fallback`.

### API (read-only, localhost-only)

| Route | Returns (abbrev.) |
|-------|-------------------|
| `GET /api/grammar/status` | `db_path`, `generated_at`, `grammars[]`, `unknown_extensions[]`, `llm_fallback` |
| `GET /api/grammar/mutations?limit=N` | `mutations[]` with `grammar_name`, `node_type`, `action`, `observed_at`, `receipt_path`, `sig_path`, `receipt_exists`, `sig_exists` |
| `GET /api/grammar/unknown-extensions` | `total`, `extensions[]` (`ext`, `first_seen_at`, optional `raw_bytes_hex`) |
| `GET /api/fabric/llm-budget` | `budget_*`, `calls_today`, `available` (often null when unset) |
| `POST /api/grammar/verify-receipt` | `verified`, `verifier_output`, `receipt_path`, `sig_path`, `verified_at` |

Non-localhost requests get **403**. Verify rejects paths outside canonical receipt dirs (**400** / **404**).

### Studio

Open **Grammar Health** in the left rail (chart icon between Receipts and Settings). Four GETs poll every 10s; **Verify** POSTs `{ "receipt_path": "<abs path>" }`.

![Grammar Health drawer](docs/images/grammar-health-drawer.png)

### Roadmap

**Slice 18d (shipped as v0.5)** — Compliance Vault foundation: signed finding receipts + ML-DSA scan manifests. See [SLICE_18d.md](slices/SLICE_18d.md).

## Compliance Vault (since v0.5)

OMNIX can emit **cryptographically signed evidence** for findings from `find-bugs`: each finding has an **Ed25519** signature; each scan has a **ML-DSA-65** signature over a **Merkle root** of finding hashes. Any changed byte, removed finding, or altered manifest should fail **`omnix axiom verify-scan`** quickly.

This is the foundation for the **Compliance Vault** tier (**in beta with design partners**) — **designed to align with** EU AI Act Article 12 (logging and traceability) and DORA Article 17 (ICT incident reporting) expectations. OMNIX is **not** a certified compliance product; it is **compliance-aligned** infrastructure that produces audit-ready evidence.

### Demo

```bash
# 1) Project Ed25519 keypair (one-time; idempotent)
omnix axiom keygen --project ~/my-codebase

# 2) Scan with signed receipts (opt-in)
omnix find-bugs ~/my-codebase --emit-receipts
# Output includes receipt path under ~/.omnix/receipts/findings/<project_id>/<scan_id>/

# 3) Verify the latest scan directory (use paths from your machine)
omnix axiom verify-scan ~/.omnix/receipts/findings/<project_id>/<scan_id>/ \
  --ed25519-pubkey ~/my-codebase/.omnix/pubkey.pem \
  --mldsa-pubkey ~/.omnix/keys/public.pem
# Example: verified  finding_count=3

# 4) Export auditor zip (keys + scans + index + README)
omnix axiom export-vault ~/my-codebase --out audit.zip
# Example: wrote audit.zip  (2 scans included, 0 excluded as tampered)
```

The zip is intended for **offline verification** by a third party using the bundled instructions and public keys.

![Compliance Vault demo](docs/videos/compliance-vault-demo.mp4)

*(Placeholder until `docs/videos/compliance-vault-demo.mp4` is recorded — see slice 18d step 4 screencast brief.)*

### API (read-only, localhost-only)

| Route | Returns |
|-------|---------|
| `GET /api/findings/scans` | `{ scans: [...] }` with `scan_id`, timestamps, `finding_count`, `dir_path_relative`, `manifest_kind` |
| `POST /api/findings/verify-scan` | Body `{ "scan_id": "..." }` → `verified`, `reason`, `finding_count`, `manifest_summary` |

Non-localhost → **403**. Malformed or traversal `scan_id` → **400**.

### Studio

**Receipts** drawer → **Finding Scans** tab: lists scans; **Verify** calls `/api/findings/verify-scan` and shows pass/fail inline.

### Tampering

One **`verify-scan`** checks: modified receipt (Merkle / sig mismatch), missing receipt vs manifest roster, invalid ML-DSA on manifest.

### Deferred public docs

Standalone verifier without a full OMNIX install is planned for **v0.6** (not in this README). Detailed regulatory mappings stay in design-partner conversations.

## What It Does

- 🔍 Parses Python + TypeScript with Tree-sitter
- 🧬 Builds a knowledge graph of every symbol and relationship
- 🌐 Renders an interactive 3D force graph in your browser
- ⚡ Click any node to see what it connects to
- 🔎 Search for any function, class, or file
- 📊 Stats: files, functions, classes, imports, edges

## Coming Soon

- AI agents that understand your product and test it like a human
- Full-stack failure tracing (UI → API → DB → root cause)
- Self-healing: OMNIX finds bugs and proposes sandbox-only fixes
- MCP server for Cursor / Claude Code integration

## Adjacent prior art (each does part of the stack)

- **tree-sitter-language-pack** — large grammar bundle (300+); no built-in signed audit trail
- **Codebase-Memory (e.g. arXiv:2603.27277, multi-language, MCP tools)** — memory/retrieval layer; not the same as ML-DSA graph-event signing in-tree
- **pqrascv-core** — ML-DSA-65 attestation patterns for embedded Rust; different product surface
- **Sigstore / cosign** — software artifact signing and provenance; OMNIX signs code-intelligence *events* with ML-DSA-65, not OCI images
- **JQF, PropTest-AI** — property-based testing and LLM assistance; OMNIX’s Layer 5–7 ties PBT to graph + optional Fabric
- **Tian AI and similar (AST + LLM)** — self-modification experiments; OMNIX keeps evolution metadata signed and does not `eval` LLM output in-process for universal PBT

## License

MIT
