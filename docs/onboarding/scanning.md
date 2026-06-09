# Scanning your codebase with OMNIX

> OMNIX is a graph-native pipeline that observes your legacy system, mines its
> behavioral spec, generates a rebuild in the target language from scratch, runs
> the rebuild through six verification gates, and emits a cryptographically
> signed receipt for every accepted unit.

This guide covers the four ways your team can point OMNIX at a codebase and
what to expect at each step.

## Availability labels

| Label | Meaning |
|---|---|
| Local available | Works from the local CLI or localhost Studio in this repository. |
| Cloud deployment required | Requires an OMNIX cloud/API deployment and tenant provisioning. |
| App/deployment surface | Code exists for this path, but marketplace publication and tenant setup are deployment-specific. |
| Enterprise/operator path | Requires customer infrastructure, operator setup, and environment-specific validation. |

## TL;DR — which path is for me?

| If you are... | Use path | Availability | Why |
|---|---|---|---|
| Evaluating OMNIX without a contract | A (tus upload) | Cloud deployment required | Tarball in, receipts out when a tenant API is provisioned. |
| Running a pilot on a private GitHub/GitLab repo | B (git clone via PAT) | Cloud deployment required | Read-only clone flow; no repo write access. |
| Adopting OMNIX across multiple repos | C (GitHub App) | App/deployment surface | Install-once workflow when the GitHub App and cloud backend are deployed. |
| Regulated industry / mainframe / air-gapped | D (Helm install + live observation) | Enterprise/operator path | Self-hosted observation and signed evidence bundle, validated per environment. |

## Path A — Tarball upload (tus 1.0.0)

The lowest-commitment evaluation path. No repo access, no GitHub App
installation, no DNS changes.

### Prerequisites
- A tenant on your OMNIX cloud instance (we provision this; one operator action)
- An API key (issued at tenant creation; rotates on demand)
- `curl` 7.79+ or the OMNIX CLI (`pip install omnix-cli` if you want a less verbose path)
- Network egress from your build environment to `app.<your-tenant>.axiomcontrol.systems`

### Procedure
```bash
# 1. Tarball your codebase. Strip build artifacts and dependencies first.
tar --exclude='target/' --exclude='node_modules/' --exclude='.git/' \
    -czf my-legacy-app.tar.gz /path/to/legacy/codebase

# 2. Initiate a tus upload
curl -X POST https://app.your-tenant.axiomcontrol.systems/v1/upload \
  -H "Tus-Resumable: 1.0.0" \
  -H "Upload-Length: $(stat -c %s my-legacy-app.tar.gz)" \
  -H "Authorization: Bearer $OMNIX_API_KEY"
# Response includes Location header: /v1/upload/<upload_id>

# 3. Upload the bytes (resumable — interrupted uploads continue from the last offset)
curl -X PATCH "https://app.your-tenant.axiomcontrol.systems/v1/upload/<upload_id>" \
  -H "Tus-Resumable: 1.0.0" \
  -H "Upload-Offset: 0" \
  -H "Content-Type: application/offset+octet-stream" \
  -H "Authorization: Bearer $OMNIX_API_KEY" \
  --data-binary "@my-legacy-app.tar.gz"

# 4. Trigger a replication job
curl -X POST https://app.your-tenant.axiomcontrol.systems/v1/jobs \
  -H "Authorization: Bearer $OMNIX_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"source":{"type":"tus","upload_id":"<upload_id>"},"target_language":"java21","mode":"production"}'
# Response: {"job_id":"<uuid>","ws_url":"wss://...","status":"queued"}
```

### What happens next
1. **Ingest** — OMNIX expands the tarball under tenant-isolated storage. Hash of the upload becomes part of every receipt.
2. **Parse** — Tree-sitter (Java/Python/TypeScript/Go/Ruby/Rust grammars active; LLM fallback for files that don't parse cleanly).
3. **Graph build** — Typed program graph in PostgreSQL, scoped to your tenant.
4. **Spec mining** — Per-node behavioral spec derived from the graph + (if Path D) live observation.
5. **Generate** — LLM dispatched via the Provider Fabric (Anthropic / Bedrock / self-hosted Llama 3.3 70B depending on your tier and data classification).
6. **Six-gate verification** — syntactic parse, type check, signature check, dependency check, property-based test, behavioral equivalence.
7. **Sign** — Each accepted unit emits an ML-DSA-65 signed receipt covering the legacy source hash, rebuilt source hash, spec version, all six gate results, the LLM model + prompt template versions.

### What you get back
- **Job state endpoint:** `GET /v1/jobs/{job_id}` — current state, gate-by-gate progress
- **Event stream:** `WSS /ws/jobs/{job_id}` — real-time gate events for your dashboards
- **Receipts:** `GET /v1/jobs/{job_id}/receipts` — list of every signed receipt
- **Public verifier:** `https://verify.your-tenant.axiomcontrol.systems/r/<receipt_id>` — shareable URL your auditor can open

## Easier: the `omnix scan` CLI

The `omnix scan` command wraps Paths A, B, and C into one verb that auto-detects what you pointed it at.

```bash
omnix scan ./path/to/codebase                 # local path → tar locally + tus upload
omnix scan https://github.com/org/repo.git    # git URL → server-side clone (Path B)
omnix scan path/to/codebase.tar.gz            # tarball → tus upload (skip the tar step)
```

Always polls for terminal state and offline-verifies every receipt against the
bundled public key. Pass `--no-wait` for fire-and-forget; `--json` for CI
integration. See `omnix scan --help` for the full flag list.

## Path B — Git clone via PAT

### Prerequisites
- A fine-grained PAT on the repo with **only** these scopes: `contents:read`, `metadata:read`.
- Repo URL (private repos supported; OMNIX never pushes back to your repo).

### Procedure
```bash
curl -X POST https://app.your-tenant.axiomcontrol.systems/v1/git/clone \
  -H "Authorization: Bearer $OMNIX_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "repo_url": "https://github.com/your-org/legacy-monolith",
    "ref": "main",
    "token": "github_pat_..."
  }'
# Response: {"job_id":"<uuid>",...}  (same shape as Path A from here)
```

OMNIX clones with `git clone --filter=blob:none --depth=1 --no-tags`. We pull
only the files needed for the scan; full repo history is not transferred.
Maximum clone size is 5GB by default (configurable per tenant tier).

## Path C — GitHub App

The self-service path. Install once, scan on push.

### Install
1. Visit `https://github.com/marketplace/omnix-replication`
2. Click Install, choose which repositories
3. Pick a plan: Free (1 repo × 5 scans/month), Team ($99/mo, 10 repos unlimited), Enterprise (sales-led)

### Trigger a scan
- **Automatic on push:** Every push to a configured branch triggers an OMNIX scan. Findings appear as a GitHub Check Run; the rebuild is opened as a new PR.
- **Manual on PR:** Comment `/omnix replicate` on any PR to scan it. Scope it with `/omnix replicate src/customer/PremiumCalculator.java`.
- **Manual on workflow_dispatch:** Add the OMNIX workflow file to `.github/workflows/` and trigger from the Actions tab.

### Permissions OMNIX requests
- `contents:read` — read repo code
- `pull_requests:write` — open PRs with rebuilds
- `checks:write` — annotate scans with Check Run results
- `metadata:read` — read repo metadata

That is the entire scope. No write access to code outside of OMNIX-authored PRs.
No access to issues, no access to projects, no access to other repos in your org.

## Path D — Helm install with live observation

The full Helm deployment with live observation. For regulated industries, mainframe shops, and
teams that need behavioral verification against real production traffic before
cutting over.

### Prerequisites
- Kubernetes 1.28+ cluster (EKS, GKE, AKS, OpenShift, on-prem)
- 8 CPU / 16 GiB minimum cluster capacity (32 CPU / 64 GiB recommended for production)
- Kernel 5.8+ on worker nodes if you want the eBPF Tetragon observation surface
- Customer-managed Kafka (Confluent Cloud, MSK, Strimzi) if you want Debezium CDC observation
- A Postgres database (Aurora, RDS, CloudSQL, or in-cluster Postgres operator)

### Install
```bash
# 1. Install the OMNIX Helm chart
helm repo add omnix https://helm.axiomcontrol.systems
helm repo update
helm install omnix omnix/omnix \
  --namespace omnix \
  --create-namespace \
  -f production-values.yaml

# 2. Provision the cluster-scoped secrets (we supply a script that runs in your CI)
omnix-installer secrets --namespace omnix --signing-key-out /secure/signing.key

# 3. Initialize the Rekor v2 transparency log (optional, for DORA / EU AI Act / CMMC / CNSA compliance)
omnix-installer rekor init --rekor-url https://omnix-rekor.your-cluster.local:3000

# 4. Open the Studio
kubectl port-forward --namespace omnix svc/omnix-api 8080:8080
open http://127.0.0.1:8080
```

### Live observation (optional, recommended for behavioral verification)
- **eBPF (Tetragon):** Enable `.Values.ebpf.tetragon.enabled=true`. OMNIX captures `tcp_connect`/`tcp_close`/`sys_execve`/file-open/DNS at the kernel layer.
- **CDC (Debezium):** Enable `.Values.observe.cdc.enabled=true` plus per-DBMS flags. OMNIX streams change data from Postgres, MySQL, SQL Server, Oracle, DB2.
- **Mainframe (subchart):** Enable `.Values.mainframe.enabled=true` and the per-vendor flag (tcVISION / Ironstream / C\Prof). Your operator pre-licenses the mainframe-side agent; OMNIX deploys the in-cluster Kafka consumer.

### Strangler-fig cutover (Path D's whole point)
Once a unit has passed all six gates and emitted a signed receipt, your
operator can shift production traffic in the Studio:

1. In the Studio, click the unit's "Cutover" affordance.
2. The CutoverModal renders the current shift state, a slider with snap points (0/1/5/10/25/50/75/100), the signed receipt preview, and the history.
3. Drag the slider, click Confirm — Envoy hot-reloads the routing table within a second.
4. Every shift is itself a signed receipt. Every shift can be rolled back; rollback is also signed.

## Reading receipts

Every accepted replication produces a JSON receipt + an ML-DSA-65 signature.
Auditors verify offline with the standalone `omnix-verify` binary:
```bash
omnix-verify \
  --receipt receipt.json \
  --signature receipt.sig \
  --pubkey omnix.pub
# Output: VALID  (sha256 match + ML-DSA-65 signature verifies against pubkey)
```

Each receipt covers:
- `legacy_source_hash` — sha256 of the original code at the unit boundary
- `rebuilt_source_hash` — sha256 of the OMNIX-generated code
- `spec_version` — the behavioral spec OMNIX mined
- `gate_results` — the six gate verdicts (and the metric each gate produced)
- `llm_provider`, `llm_model`, `prompt_template_version`
- `signature` — ML-DSA-65 (FIPS 204) signature over a canonical JSON encoding
- `pubkey_fingerprint` — cosign-compatible

For customers mapping evidence to DORA, EU AI Act Article 12, CMMC, or CNSA
programs, receipts can be uploaded to a private transparency log and included
in the audit bundle. That supports traceability review; it is not a
certification or blanket compliance claim.

## What OMNIX is not

- **Not an autonomous agent.** Your operator drives every cutover. The LLM
  never decides what's "good enough"; the six gates do.
- **Not a proof of correctness.** The gates produce strong evidence. Receipts
  produce a tamper-evident record. None of that is mathematical proof.
- **Not a transpiler.** OMNIX rebuilds from scratch in the target language
  against the mined spec, not via AST-level source-to-source transformation.

## Support
- Pilot scoping: open an issue at github.com/gowdaharshith1998-lang/OMNIX
- Compliance questions (DORA, EU AI Act, CMMC, CNSA): same channel
- Security disclosure: same channel — we'll provide an encrypted channel on request
