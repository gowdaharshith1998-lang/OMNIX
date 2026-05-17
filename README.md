# OMNIX

**OMNIX is the graph-native platform for migrating legacy systems to modern stacks with verified behavioral equivalence and full data fidelity, running in parallel with the legacy system until the organization is ready to cut over.**

If you run an engineering org with a 30-year-old Java estate, a regulator on your back, and a talent shortage on the COBOL/Spring-2.x side, OMNIX is the tooling layer that lets your team migrate one structurally-bounded node at a time, verify each rebuilt node against the legacy one with a six-gate evidence pipeline, and ship the result with a signed audit trail your compliance team can hand to an examiner.

---

## Why this exists

The companies we built OMNIX for share a profile:

- 5-30 year old codebase in Java 6/7/8, .NET Framework, COBOL, or similar
- Mandate to modernize (regulatory deadline, mainframe end-of-life, cloud migration, M&A integration, or compounding talent shortage)
- $20M-$200M consulting alternative (Accenture / IBM / Deloitte / Capgemini) with the industry's ~60% project failure rate
- Internal team that tried once and bounced

OMNIX is built to be deployed by your engineering leadership — the VP Eng or platform lead who owns a bounded modernization workstream and needs to ship one production module without breaking anything, then point at the receipts when the regulator asks how they know.

---

## How it works

OMNIX is a graph-driven pipeline. It is not an autonomous agent. It is closer to a compiler with an LLM as one of its passes, and hard verification gates between every step.

```
[Legacy Codebase]
       ↓
[1. Parse → semantic graph]              ← shipped
       ↓
[2. Topological sort]                    ← shipped (graph traversal)
       ↓
[3. Generate per-node rebuild spec]      ← in progress (M1)
       ↓
[4. LLM dispatch with spec + deps]       ← orchestrator in progress (M1)
       ↓
[5. Verification gate (6 checks)]        ← gates 1-4 shipped, 5-6 in progress
       ↓ (fail → retry with error context)
       ↓ (still fail → flag for human)
[6. Sign receipt (ML-DSA)]               ← shipped (omnix.receipts subsystem)
       ↓
[7. Repeat up the graph]
       ↓
[Rebuilt codebase + signed audit trail]
```

The six verification gates are syntactic parse, type check, signature check, dependency check, property-based test, and behavioral equivalence test (legacy node vs rebuilt node, diff outputs). Each accepted node emits a signed receipt covering the legacy source hash, rebuilt source hash, spec version, all six gate results, the LLM model and prompt template versions, and the cryptographic signature. The `omnix.receipts` subsystem (ML-DSA-65 signatures, formerly named AXIOM internally) handles the signing and exposes a verifier so auditors can confirm receipt authenticity offline.

The shadow bridge (in progress, M4) routes a configurable percentage of production traffic to the rebuilt code without serving the response, diffs the outputs against the legacy path, and emits a signed receipt per request. This is how you build a year-long evidence record before any cutover.

We say "verified equivalence with auditable evidence." We do not say "provable" or "100% accurate." The gates produce strong evidence; receipts produce a tamper-evident record; the bridge surfaces divergence in production. None of that is a mathematical proof, and we will not market it as one.

---

## Competitive context

Java modernization is a contested category. Be honest about the incumbents:

- **Amazon Q Code Transformation** ships Java 8/11/17 → 17/21 upgrade workflows with build/test loops and transformation plans, bundled into AWS migration budgets and developer tooling.
- **OpenRewrite** (open source) and **Moderne** (commercial) own deterministic recipe-driven Java modernization — `javax → jakarta`, Spring Boot 2 → 3, dependency upgrades — with enterprise-scale rollout dashboards.
- **Accenture / IBM / Deloitte / Capgemini** run the multi-million-dollar program-management layer.

OMNIX does not compete with these on the LLM transformation step. The LLM step uses standard frontier models (Anthropic, OpenAI) or local/on-prem (Llama 3.1 70B + vLLM) for regulated buyers. OMNIX's defensibility lives in the layer the incumbents do not ship: a verification gate that combines deterministic checks with property-based testing and side-by-side behavioral diffing, a receipt-linked shadow bridge that produces an auditable production-traffic record over time, and a graph-driven blast-radius model that quantifies which changes are safe to merge.

If you are already running Amazon Q or OpenRewrite, the right shape is to let them generate the transformation and let OMNIX produce the gate results, the signed receipt per accepted node, and the shadow-bridge evidence your compliance team needs. We are the layer that makes someone else's migration reviewable with an evidence trail.

---

## What works today (v0.6)

The current release is foundational scaffolding for the full pipeline. CLI surface:

```bash
# Parse a codebase into the OMNIX graph
omnix analyze /path/to/project

# Property-based tests with optional signed finding receipts
omnix find-bugs /path/to/project --emit-receipts

# Behavioral verification gates against the graph
omnix verify /path/to/project

# Parser grammar visibility
omnix grammar status
omnix grammar list

# Signed-receipt verification + audit export
omnix axiom keygen --project /path/to/project
omnix axiom verify-scan /path/to/receipts/dir \
  --ed25519-pubkey <pubkey> --mldsa-pubkey <pubkey>
omnix axiom export-vault /path/to/project --out audit.zip
```

What ships in v0.6 specifically:

- Universal Tree-sitter-based parser producing the semantic graph — 6 grammars active (Python, TypeScript, Java, Go, Ruby, Rust), enumerable via `omnix grammar list`. Python and TypeScript additionally have language-specialist passes for richer symbol resolution; the rest fall through to the universal tree-sitter pipeline. Files tree-sitter cannot parse are caught by an LLM fallback.
- Property-based testing with signed finding receipts (Ed25519 per-finding + ML-DSA-65 over a Merkle root per scan)
- Behavioral verification primitives (subprocess-isolated, forkserver-safe, hygiene-aware)
- Read-only localhost API + a React studio for inspection
- Audit export bundle ready for offline third-party verification

Built but not yet exposed as polished CLI verbs (M1-M2): the spec generator, the LLM orchestrator, the dual-runtime equivalence runner. Coming in subsequent milestones (M3-M5): the engineer-review workspace, the shadow bridge, the regulator-facing audit explorer, and the standalone verifier binary that auditors can run without installing the full Python stack.

---

## Roadmap milestones

The milestones below come from the OMNIX build map. Dates are intentionally not promised — the team is small and the work is honest.

| Milestone | Scope |
|---|---|
| **M0.5** | Land slice 15.3.7 LLM tool-dispatch into the `omnix.fabric` / `omnix.providers` namespace |
| **M1** | End-to-end single-node migration: spec generator v1, LLM orchestrator, gates 1-4, signed receipt — one Java 6 function → Java 21 |
| **M2** | Whole-module migration on a real OSS Java codebase, with gate 5 (property) and gate 6 (behavioral) producing diffs |
| **M3** | Engineer-review workspace: triage queue for nodes that fail verification, side-by-side diff with annotated gates, keyboard-driven approve/re-run/edit |
| **M4** | Shadow bridge: runs rebuilt code on production traffic without serving the response, signed receipt per request, divergence alerting |
| **M5** | Executive dashboard (RAG verdict + top risk) and regulator-facing audit explorer with PDF export |

Standalone `omnix-verify` binary (Go or Rust, ~5MB, no Python required) ships alongside M1 so auditors can verify a receipt offline on day one.

---

## Quick start

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

The analyze command parses the codebase, builds the graph, and starts the React studio on localhost. Studio ingests into `<path>/.omnix/omnix.db`.

Use `python omnix.py analyze /path --no-open` to start the studio server without launching a browser.

---

## Signed receipts and audit export

OMNIX can emit cryptographically signed evidence for findings from `find-bugs`: each finding gets an Ed25519 signature; each scan gets a ML-DSA-65 signature over a Merkle root of finding hashes. Any changed byte, removed finding, or altered manifest fails `omnix axiom verify-scan` quickly.

This is the foundation for the receipt-linked audit trail the rest of the pipeline plugs into. The current release ships:

- **Localhost-only API** — `GET /api/findings/scans`, `POST /api/findings/verify-scan` (non-localhost → 403)
- **Studio Receipts drawer** with a Finding Scans tab; Verify calls `/api/findings/verify-scan` and shows pass/fail inline
- **`omnix axiom export-vault`** — produces an offline-verifiable zip with keys, scans, index, and instructions for a third party

The audit trail is *compliance-aligned infrastructure that produces evidence suitable for review*. OMNIX is not a certified compliance product. The design is intended to align with EU AI Act Article 12 (logging and traceability) and DORA Article 17 (ICT incident reporting) expectations, but the certification path is the buyer's, not ours.

---

## Adjacent and overlapping tools

- **Amazon Q Code Transformation** — Java upgrade workflow; OMNIX produces the audit layer over its output
- **OpenRewrite / Moderne** — recipe-driven deterministic refactor; OMNIX produces the receipt and shadow evidence over their output
- **AWS DMS / Azure DMS / GCP DTS** — bulk database migration and CDC; OMNIX uses these for the data-side of a parallel-run rather than rebuilding them
- **Envoy / Apache Camel / Argo Rollouts** — traffic routing, protocol mediation, progressive delivery; OMNIX's shadow bridge runs alongside these rather than replacing them
- **Sigstore / cosign** — software artifact signing; OMNIX signs code-intelligence events and per-node receipts with ML-DSA-65, a different surface
- **Tree-sitter language packs** — grammar bundles; OMNIX consumes these and adds the symbol-resolution, signed-event, and verification layers on top
- **JQF, PropTest-AI** — property-based testing tooling; OMNIX integrates property tests as gate 5 of the verification pipeline

---

## License

MIT
