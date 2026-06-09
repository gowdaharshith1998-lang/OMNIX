# OMNIX

A graph-native pipeline for migrating legacy systems to modern stacks. OMNIX parses your codebase into a typed program graph, rewrites it one structurally-bounded node at a time with an LLM as one of its passes, runs each rebuild through a six-gate verification pipeline, and emits a cryptographically signed receipt covering every transformation. No black-box rewrites, no opaque diffs, nothing you have to take on faith.

Built by [Harshith Gowda](https://github.com/gowdaharshith1998-lang) as a source-visible engineering portfolio and commercial product prototype. The repo is public so reviewers can inspect the architecture, tests, CI, signed-receipt system, parser stack, service surfaces, and deployment work directly.

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

That's the full bootstrap. It parses the codebase, builds the graph, and starts a local React studio so you can poke at the result before you let anything else touch your code.

---

## For hiring reviewers

I built OMNIX to show the kind of systems work I can own end to end: graph-native code analysis, Tree-sitter ingestion, verification gates, property-based testing, source-available product packaging, cloud/API surfaces, GitHub automation, and post-quantum signed audit receipts.

The shortest portfolio framing is:

> I built OMNIX: a graph-native legacy-modernization engine with six-gate verification and post-quantum signed receipts for every finding or transformation.

A 60-second recording script is available in [`docs/demo/60-second-demo.md`](docs/demo/60-second-demo.md). It shows analyze, bug scan with receipt emission, successful receipt verification, and a tamper-fail moment.

---

## Project status

OMNIX is active source-visible commercial software at `v0.6.1`. The local
code-intelligence and signed-receipt surfaces are the most mature parts of the
repo. Rebuild orchestration, hosted cloud scanning, GitHub App automation, and
enterprise deployment are present as implementation tracks, demos, or
private-pilot surfaces.

| Surface | Current status |
|---|---|
| Local graph analysis, grammar visibility, bug scanning, signed finding receipts, and audit export | Available in the local CLI / Studio path |
| Single-node Java rebuild demo | Available as an M1 demo flow; see `docs/M1_DEMO.md` |
| Full multi-node rebuild orchestration | In progress |
| OMNIX-DM data migration phases D1-D5 | Implemented and documented in stages; see `docs/dm/` |
| Hosted cloud scanning, GitHub App, and Helm/airgap deployment | Private-pilot or enterprise deployment surfaces, not a public self-serve service from this repo alone |

---

## What it actually does

OMNIX is not an autonomous agent. It is closer to a compiler with an LLM as one of its passes, and hard verification gates between every step.

```
parse → typed program graph                       [shipped]
topo-sort                                         [shipped]
generate per-node rebuild spec                    [M1 demo / in progress]
LLM dispatch with spec + dependency context       [M1 demo / in progress]
6-gate verification                               [gates 1–4 in M1 demo, 5–6 in progress]
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

The claim is **verified equivalence with auditable evidence**. Not "provable," not "100% accurate." The gates produce strong evidence; receipts produce a tamper-evident record; the shadow bridge (M4) surfaces divergence on real production traffic. None of that is mathematical proof, and this repo does not market it as one.

---

## Who this is for

If you are running an engineering org with:

- a 5-to-30-year-old codebase in Java 6/7/8, .NET Framework, or COBOL
- a regulatory deadline, mainframe end-of-life, cloud migration, or M&A timeline
- a quote from Accenture / IBM / Deloitte / Capgemini that's somewhere between $20M and $200M, and an industry failure rate near 60%
- one internal team that tried once and bounced

OMNIX is built for the VP Eng who has to ship one production module without breaking anything, then point at the receipts when an auditor asks how they know it's equivalent. A buyer's team can drive the local pipeline directly, or a private pilot can be scoped around a first module.

---

## OMNIX-DM — data migration layer

OMNIX-DM is the data-migration layer beneath the code replicator. Its outputs
are signed, inspectable migration artifacts, not a claim of automatic or
mathematically proven migration correctness.

Current status by phase:

| Phase | Status | Artifact |
|---|---|---|
| D1 Schema Understanding | Available in the DM library surface | signed `column-mapping.json` |
| D2 Edge-Case Profiling | Available in the DM library surface | signed `edge-case-manifest.json` |
| D3 Transformation Synthesis | Present in the current tree; treat as unreleased until packaged | signed `TransformerSpec` or halt receipt |
| D4 Bulk Import | Present in the current tree; operator-run and preconditioned | signed batch and quarantine receipts |
| D5 Change Data Capture | Present for PostgreSQL CDC; Oracle/MySQL adapters are explicit stubs | sampled CDC receipts, lag reports, cutover proposal |

Built on the Wang/Dillig UT Austin trilogy (Mediator POPL 2018 / Migrator
arXiv 1904.05498 / Dynamite PVLDB 2020). The current product surfaces signed
evidence, explicit gaps, and operator-review points. A Z3-backed formal
verification layer remains future work and should not be marketed as a current
capability.

See [`docs/dm/`](docs/dm/) for the full pipeline walkthrough, academic
foundation, and runbook.

---

## Ways to run it

OMNIX can be evaluated locally as a tool, or scoped as a private pilot around a real migration target.

**Run the local evaluation path yourself.** Install the CLI, point it at your
codebase, and inspect the graph, findings, receipts, and local Studio.
Everything runs on your infrastructure unless you configure a hosted LLM
yourself. Everything in **What works today** below is the self-serve surface.

**Run a private pilot or enterprise deployment.** Hosted scanning, the GitHub
App, Helm/airgap deployment, and shadow-bridge cutover are private-pilot or
enterprise surfaces. They require project scoping, tenant configuration, and
deployment decisions outside this repository.

Private pilots are scoped by codebase size, target language, and how deep into the pipeline the buyer wants to go. The typical path is one migrated module first, then an internal handoff once the buyer's team has reps. Some deployments keep the shadow-bridge side active through cutover.

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

## What works today (v0.6.1)

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

In v0.6.1 specifically:

- **Universal Tree-sitter parser** producing the semantic graph. Six grammars active today (Python, TypeScript, Java, Go, Ruby, Rust); run `omnix grammar list` to see them. Python and TypeScript additionally have specialist passes for richer symbol resolution. Files Tree-sitter cannot parse drop to an LLM fallback.
- **Property-based testing** with signed finding receipts. Ed25519 per finding, ML-DSA-65 over a Merkle root per scan.
- **Behavioral verification primitives** — subprocess-isolated, forkserver-safe, hygiene-aware.
- **Read-only localhost API** with a React studio for inspection.
- **Audit export bundle** — an offline zip your auditor's auditor can verify without installing the full Python stack.

Available as demo or active implementation work, but not yet a polished general
CLI surface: the spec generator, the LLM orchestrator, and the dual-runtime
equivalence runner.

---

## Roadmap

The project is intentionally scoped around milestones, not dates.

| Milestone | Scope |
|---|---|
| **M0.5** | LLM tool-dispatch landed in the `omnix.fabric` / `omnix.providers` namespace |
| **M1** | End-to-end single-node migration. Spec generator v1, orchestrator, gates 1–4, signed receipt. One Java 6 function → Java 21. |
| **M2** | Whole-module migration on a real OSS Java codebase, with gate 5 (property) and gate 6 (behavioral) producing diffs. |
| **M3** | Engineer-review workspace. Triage queue for failing nodes, side-by-side diff with annotated gates, keyboard-driven approve / re-run / edit. |
| **M4** | Shadow bridge. Runs rebuilt code against production traffic without serving the response, signed receipt per request, divergence alerting. |
| **M5** | Executive dashboard and regulator-facing audit explorer with PDF export. |

See [`docs/PHASES.md`](docs/PHASES.md) for the full completed/current/planned
phase map.

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

Built by [@gowdaharshith1998-lang](https://github.com/gowdaharshith1998-lang). Issues are open for evaluation questions, demo requests, and licensing inquiries.

---

## License

OMNIX is source-available, not open source. Source is visible for evaluation and review; commercial use, redistribution, hosted use, or derivative product use requires a license. See [`LICENSE.md`](LICENSE.md) and [open an issue](https://github.com/gowdaharshith1998-lang/OMNIX/issues) for licensing inquiries.
