# GitHub Marketplace listing — OMNIX Replication

## Tagline

Modernize Java 6/7 to Java 21 with verifiable behavioral equivalence.

## Categories

- code-quality
- dependency-management

## Description

OMNIX is a behavioral replicator for legacy Java codebases. Install the
GitHub App, push to your default branch, and OMNIX opens a pull request
with Java 21 generated from scratch — accompanied by a cryptographically
signed receipt that proves the generated code is behaviorally equivalent
to your existing code.

The replication runs four equivalence verifiers in parallel:

1. **Hypothesis** — property-based tests on generated functions
2. **Scientist** — in-process dual-run during canary cutover
3. **Diffy** — service-boundary diff with primary-vs-secondary noise filter
4. **Daikon-lite** — invariant re-mining on the candidate

Every signed receipt is verifiable independently at
`verify.axiomcontrol.systems` via a WASM-loaded ML-DSA-65 verifier. The
signature algorithm is FIPS 204 — compliant with the NIST PQC migration
mandate (2030) and CNSA 2.0 (2035) ahead of schedule.

## Pricing

| Plan | Price | Description |
|---|---|---|
| Free | $0 | 1 private repo, 5 replication runs / month |
| Team | $99 / month / org | 10 private repos, unlimited runs, private verifier |
| Enterprise | Custom | Air-gapped Helm install, signed audit kit, SLA |

## Permissions requested

- **Repository contents** (read): so we can analyze your codebase
- **Pull requests** (write): so we can open replication PRs
- **Checks** (write): so we can publish equivalence check runs
- **Metadata** (read): so we can list your repositories

## Events subscribed

- `push`
- `pull_request`
- `issue_comment` (for `/omnix replicate` slash command)
- `installation`
- `installation_repositories`

## Screenshots

1. OMNIX-generated PR on the user's repo with signed receipts in the body
2. `verify.axiomcontrol.systems` public verifier page (WASM verify in
   <500ms)
3. Studio cloud view showing live job progress with all four verifiers
   green

## FAQ

- Q. Do you ever modify my code?
  A. No. OMNIX only opens PRs. Merging is your decision.

- Q. Do you train models on my code?
  A. No. We replicate per-tenant per-job. No data leaves your tenant
  scope.

- Q. What if my data residency requires AWS or EU?
  A. Choose the S3 + CMK backend (AWS residency) or set `region=eu-west-1`
  for the EU. Enterprise tier offers an air-gapped Helm deploy.
