# axiomcontrol.systems — landing copy

> Source-of-truth Markdown for the marketing site. HTML rendering lives in
> the separate `marketing-site` deployment (out of repo scope).

## Hero

**The behavioral replicator for legacy modernization.**

Java 6 → Java 21. COBOL → Java/Go/Rust. With cryptographically signed
evidence for behavioral review. No translation. No black-box rewrites.

[ Try it now → ]  [ Install GitHub App → ]

---

## How it differs

| | OMNIX | Translation tools | Translation services |
|---|---|---|---|
| Approach | Observes legacy, generates from-scratch in target | AST-walking transpiler | LLM rewrite + manual review |
| Behavioral evidence | ML-DSA-65 signed receipt per unit | Usually absent | Usually manual |
| PQC-ready signing primitive | ML-DSA-65 / FIPS 204 | Varies | Varies |
| EU AI Act Article 12 support | Structured logs and receipt trail | Varies | Manual |
| DORA evidence support | Signed artifacts and optional retention via Rekor | Varies | Manual |
| Behavior verifiers | Hypothesis + Scientist + Diffy + Daikon | – | Manual |
| Public verifier page | ✓ WASM, client-side | – | – |

## The signed evidence trail

Every replicated unit produces a signed receipt:

    {
      "job_id":     "j-7421",
      "unit_id":    "checkout.OrderService",
      "src_lang":   "java6",
      "target":     "java21",
      "verifiers":  {
        "hypothesis_passed":      true,
        "scientist_mismatches":   0,
        "diffy_mismatches":       0,
        "daikon_violated":        0,
        "daikon_agreed":         28
      },
      "signed_at":  "2026-05-20T14:21:00Z"
    }

Signature: **ML-DSA-65 (FIPS 204)**. Verifiable client-side at
`verify.axiomcontrol.systems/r/<id>`.

Hypercubic, Mechanical Orchard, AWS Transform, IBM Bob, Phase Change,
Moderne — **none of them sign their migration outputs**. OMNIX does. That
is the moat no competitor can match without a six-month engineering
investment.

## Pricing

| Plan | Price | What you get |
|---|---|---|
| Free | $0 / month | 1 private repo, 5 replication runs / month, public verifier page |
| Team | $99 / month / org | 10 private repos, unlimited runs, private verifier instance |
| Enterprise | $25K–$75K snapshot pilot | Air-gapped Helm install, BYO CMK, signed audit kit, SLA |

## Forcing functions on the buyer's calendar

- **EU AI Act Article 12** — Aug 2 2026 (or Dec 2 2027 under Omnibus VII)
- **DORA Article 6** — already in force
- **NIST PQC migration** — 2030
- **CNSA 2.0 quantum-resistant crypto** — 2035

ML-DSA-65 is the signing primitive OMNIX uses for receipt integrity. It can
support PQC migration planning and audit evidence programs, but compliance
depends on the buyer's deployment, controls, retention policy, and legal
review.
