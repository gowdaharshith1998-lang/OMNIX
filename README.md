# OMNIX

A graph-native pipeline for migrating legacy systems to modern stacks. OMNIX parses your codebase into a typed program graph, rewrites it one structurally-bounded node at a time with an LLM as one of its passes, runs each rebuild through a six-gate verification pipeline, and emits a cryptographically signed receipt covering every transformation. No black-box rewrites, no opaque diffs, nothing you have to take on faith.

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

That's the full bootstrap. It parses the codebase, builds the graph, and starts a local React studio so you can poke at the result before you let anything else touch your code.

---

## What it actually does

OMNIX is not an autonomous agent. It is closer to a compiler with an LLM as one of its passes, and hard verification gates between every step.

```
parse → typed program graph                       [shipped]
topo-sort                                         [shipped]
generate per-node rebuild spec                    [M1, in progress]
LLM dispatch with spec + dependency context       [M1, in progress]
6-gate verification                               [gates 1–4 shipped, 5–6 in progress]
  ├─ 1. syntactic parse        deterministic
  ├─ 2. type check             deterministic
  ├─ 3. signature check        deterministic
  ├─ 4. dependency check       deterministic
  ├─ 5. property-based test    Hypothesis / JQF
  └─ 6. behavioral equivalence legacy vs rebuilt, diffed
sign receipt (ML-DSA-65 + Ed25519)                [shipped]
repeat up the graph
```

If a gate fails, OMNIX retries the LLM with the failure as additional context. If it still fails, the node is flagged for human review — not silently retried until something happens to compile. The receipt records that too.

Each accepted node emits a signed receipt covering:
- legacy source hash
- rebuilt source hash
- spec version
- all six gate results
- LLM model + prompt template versions
- a cryptographic signature any third party can verify offline

We say **verified equivalence with auditable evidence**. We do not say "provable" or "100% accurate." The gates produce strong evidence; receipts produce a tamper-evident record; the shadow bridge (M4) surfaces divergence on real production traffic. None of that is mathematical proof, and we will not market it as one.

---

## Who this is for

If you are running an engineering org with:

- a 5-to-30-year-old codebase in Java 6/7/8, .NET Framework, or COBOL
- a regulatory deadline, mainframe end-of-life, cloud migration, or M&A timeline
- a quote from Accenture / IBM / Deloitte / Capgemini that's somewhere between $20M and $200M, and an industry failure rate near 60%
- one internal team that tried once and bounced

OMNIX is built for the VP Eng who has to ship one production module without breaking anything, then point at the receipts when an auditor asks how they know it's equivalent. Your team can drive the pipeline themselves, or we can drive it for you — see below.

---

## OMNIX-DM — data migration layer (early)

OMNIX-DM is the data-migration layer beneath the code replicator. **PR A**
ships the first two phases:

- **D1 — AI Schema Understanding** — dialect-aware DDL parsing (Postgres /
  MySQL / Oracle / MongoDB), per-column semantic embeddings, Hungarian
  optimal matching with confidence scores, ML-DSA-65 signed
  `column-mapping.json`.
- **D2 — AI Edge-Case Profiling** — expected-free-energy probe planner +
  six probers (NULL distribution, encoding anomaly, orphan FK, timezone
  drift, precision boundary, sentinel value), ML-DSA-65 signed
  `edge-case-manifest.json` chained to D1.

Built on the Wang/Dillig UT Austin trilogy (Mediator POPL 2018 / Migrator
arXiv 1904.05498 / Dynamite PVLDB 2020). PR A is the AI proposal layer;
the formal proof layer (Z3-discharged bisimulation over TRA) lands in
PR E. We do not market the "100% perfect migration" claim as proven
today — it is the destination of the trilogy productisation, not a
current capability of PR A.

See [`docs/dm/`](docs/dm/) for the full pipeline walkthrough, academic
foundation, and runbook.

---

## Two ways to run it

OMNIX is both a tool and a team.

**Run it yourself.** Install the CLI, point it at your codebase, drive the migration in-house. Everything runs on your infrastructure — code, graph, receipts, keys. Nothing leaves your perimeter unless you wire it to a hosted LLM yourself. Everything in **What works today** below is what your engineers get.

**Have us run it.** If your team doesn't have the bandwidth or the modernization reps — most don't, this is a once-per-career project — we take the whole thing end-to-end. Spec definition for your domain. LLM dispatch. Gate triage. The engineer-review workspace. Shadow-bridge deployment against production traffic. Cutover plan and rollback rehearsal. And the signed audit bundle you hand to a regulator at the end. Your engineers can review every step or stay out of it; the receipts are the same either way.

We charge per engagement, scoped by codebase size, target language, and how deep into the pipeline you want us. Most VP Engs take the service tier for the first migrated module, then move the rest in-house once their team has reps. Some keep us on the shadow-bridge side through cutover.

[Open an issue](https://github.com/gowdaharshith1998-lang/OMNIX/issues) if you want a scoping call.

---

## Where it fits next to the incumbents

Java modernization is contested. Be honest:

| Tool | Strength | Where OMNIX sits |
|---|---|---|
| **Amazon Q Code Transformation** | Java 8/11/17 → 17/21 upgrade flows, bundled into AWS migration budgets | OMNIX produces the audit layer over Q's output |
| **OpenRewrite / Moderne** | Deterministic recipe-driven refactors (`javax → jakarta`, Spring Boot 2 → 3) | OMNIX produces the receipt and shadow-traffic evidence over recipe output |
| **Accenture / IBM / Deloitte / Capgemini** | Multi-million-dollar program management | OMNIX is the tooling your VP Eng runs *instead*, not alongside |

OMNIX does not compete on the LLM transformation step. The LLM step uses standard frontier models (Anthropic, OpenAI) or local/on-prem (Llama 3.1 70B + vLLM) for regulated buyers. OMNIX's defensibility lives one layer up: a verification gate that combines deterministic checks with property-based testing and behavioral diffing, a receipt-linked shadow bridge that produces an auditable production-traffic record over time, and a graph-driven blast-radius model that quantifies which changes are safe to merge.

If you are already running Amazon Q or OpenRewrite, the right shape is to let them generate the transformation and let OMNIX produce the gate results, the signed receipts, and the shadow-bridge evidence your compliance team needs.

---

## What works today (v0.6)

```bash
# Parse a codebase into the OMNIX graph
omnix analyze /path/to/project

# Property-based bug scan, with optional signed receipts
omnix find-bugs /path/to/project --emit-receipts

# Behavioral verification gates against the graph
omnix verify /path/to/project

# Parser grammar visibility
omnix grammar status
omnix grammar list

# Signed-receipt verification + offline audit export
omnix axiom keygen --project /path/to/project
omnix axiom verify-scan /path/to/receipts/dir \
  --ed25519-pubkey <pubkey> --mldsa-pubkey <pubkey>
omnix axiom export-vault /path/to/project --out audit.zip
```

In v0.6 specifically:

- **Universal Tree-sitter parser** producing the semantic graph. Six grammars active today (Python, TypeScript, Java, Go, Ruby, Rust); run `omnix grammar list` to see them. Python and TypeScript additionally have specialist passes for richer symbol resolution. Files Tree-sitter cannot parse drop to an LLM fallback.
- **Property-based testing** with signed finding receipts. Ed25519 per finding, ML-DSA-65 over a Merkle root per scan.
- **Behavioral verification primitives** — subprocess-isolated, forkserver-safe, hygiene-aware.
- **Read-only localhost API** with a React studio for inspection.
- **Audit export bundle** — an offline zip your auditor's auditor can verify without installing the full Python stack.

Built but not yet exposed as polished CLI verbs (lands in M1–M2): the spec generator, the LLM orchestrator, the dual-runtime equivalence runner.

---

## Roadmap

The team is small and the work is honest. Milestones, not dates.

| Milestone | Scope |
|---|---|
| **M0.5** | LLM tool-dispatch landed in the `omnix.fabric` / `omnix.providers` namespace |
| **M1** | End-to-end single-node migration. Spec generator v1, orchestrator, gates 1–4, signed receipt. One Java 6 function → Java 21. |
| **M2** | Whole-module migration on a real OSS Java codebase, with gate 5 (property) and gate 6 (behavioral) producing diffs. |
| **M3** | Engineer-review workspace. Triage queue for failing nodes, side-by-side diff with annotated gates, keyboard-driven approve / re-run / edit. |
| **M4** | Shadow bridge. Runs rebuilt code against production traffic without serving the response, signed receipt per request, divergence alerting. |
| **M5** | Executive dashboard and regulator-facing audit explorer with PDF export. |

A standalone `omnix-verify` binary (Go or Rust, ~5MB, no Python required) ships alongside M1 so an auditor can verify a receipt offline on day one.

---

## Signed receipts and audit export

`omnix find-bugs --emit-receipts` already emits cryptographically signed evidence: each finding gets an Ed25519 signature; each scan gets an ML-DSA-65 signature over a Merkle root of the finding hashes. Any changed byte, removed finding, or altered manifest fails `omnix axiom verify-scan` quickly.

This is the foundation the rest of the pipeline plugs into. Today you get:

- **Localhost-only API** — `GET /api/findings/scans`, `POST /api/findings/verify-scan`. Non-localhost requests get a 403.
- **Studio Receipts drawer** with a Finding Scans tab. Verify hits `/api/findings/verify-scan` and shows pass/fail inline.
- **`omnix axiom export-vault`** — an offline-verifiable zip with keys, scans, index, and instructions for a third party.

OMNIX is **compliance-aligned infrastructure that produces evidence suitable for review**. It is not a certified compliance product. The design is intended to align with EU AI Act Article 12 (logging and traceability) and DORA Article 17 (ICT incident reporting), but the certification path is the buyer's, not ours.

---

## Adjacent tools

Tools OMNIX integrates with or sits next to:

- **Amazon Q Code Transformation** — Java upgrade workflow; OMNIX produces the audit layer over its output.
- **OpenRewrite / Moderne** — recipe-driven deterministic refactor; OMNIX produces the receipt and shadow evidence over their output.
- **AWS DMS / Azure DMS / GCP DTS** — bulk database migration and CDC; OMNIX uses these for the data-side of a parallel-run rather than rebuilding them.
- **Envoy / Apache Camel / Argo Rollouts** — traffic routing, protocol mediation, progressive delivery; OMNIX's shadow bridge runs alongside these rather than replacing them.
- **Sigstore / cosign** — software artifact signing; OMNIX signs per-node receipts with ML-DSA-65, a different surface.
- **Tree-sitter grammars** — OMNIX consumes these and adds symbol resolution, signed events, and verification on top.
- **JQF, PropTest-AI** — property-based testing; OMNIX integrates property tests as gate 5.

---

## Try it on something small

The fastest way to evaluate OMNIX is to point it at a real codebase you already have and see what falls out:

```bash
git clone https://github.com/gowdaharshith1998-lang/OMNIX.git
cd OMNIX
pip install -r requirements.txt
python omnix.py analyze ../some-java-or-python-repo
```

The studio opens on `http://127.0.0.1:7777`. Click around. Nothing is written back to your repo; the graph lives under `<your-repo>/.omnix/omnix.db`. Use `--no-open` if you only want the API.

Then run `omnix find-bugs <your-repo> --emit-receipts` and look at the receipts under `<your-repo>/.omnix/receipts/`. That is the shape of every artifact OMNIX will produce for you, scaled up.

If you want to talk to whoever is building this: [@gowdaharshith1998-lang](https://github.com/gowdaharshith1998-lang) on GitHub. Issues are open.

---

## License

All rights reserved. Source is visible for evaluation and review; commercial use requires a license. [Open an issue](https://github.com/gowdaharshith1998-lang/OMNIX/issues) for licensing inquiries.
