# OMNIX air-gapped deployment guide

This guide installs OMNIX into a customer-controlled Kubernetes cluster with no
internet egress.

## Status

This is an enterprise/operator deployment path. It requires a prepared OMNIX
air-gap bundle, customer infrastructure, and environment-specific validation.
The receipts and private transparency-log options support audit review; they do
not by themselves certify regulatory compliance.

## Prerequisites

- Kubernetes 1.28+
- A default `StorageClass` with `WaitForFirstConsumer` binding
- 8+ CPU cores, 16+ GiB memory cluster-wide (production: 32+ cores, 64+ GiB)
- Linux kernel 5.8+ on all nodes (required for the optional Tetragon eBPF
  observation pipeline; not required for codebase-only ingestion)
- An OCI registry inside the air-gap that can host the bundled images
- The OMNIX air-gap bundle:
  `omnix-airgap-<version>.airgap` + `omnix-airgap-<version>.airgap.sha256` +
  `omnix-airgap-<version>.airgap.sig`

## Verify the bundle

```bash
sha256sum -c omnix-airgap-<version>.airgap.sha256
```

Before loading images into the registry, verify
`omnix-airgap-<version>.airgap.sig` with the release public key supplied by the
OMNIX release process.

## Load images into your registry

```bash
tar -xzf omnix-airgap-<version>.airgap -C /tmp/omnix
for img in /tmp/omnix/images/*.tar; do
    docker load -i "$img"
done
# Tag and push to your internal registry
for img in omnix-cloud-api omnix-studio omnix-verifier; do
    docker tag "ghcr.io/gowdaharshith1998-lang/${img}:<version>" \
               "registry.internal/omnix/${img}:<version>"
    docker push "registry.internal/omnix/${img}:<version>"
done
```

## Install via Helm

```bash
helm install omnix /tmp/omnix/helm/omnix-<version>.tgz \
  --namespace omnix --create-namespace \
  --set global.image.registry=registry.internal/omnix \
  -f production-values.yaml
```

A `production-values.yaml` example:

```yaml
api:
  replicaCount: 4
worker:
  replicaCount: 8
postgres:
  enabled: false        # use the external Aurora cluster
redis:
  enabled: false        # use the external ElastiCache cluster
llm:
  selfHosted:
    enabled: true
    gpus:
      requested: 4
ingress:
  hosts:
    - host: app.bank.example.com
      paths: [{path: /, pathType: Prefix, service: api}]
    - host: verify.bank.example.com
      paths: [{path: /, pathType: Prefix, service: verifier}]
```

## Install via KOTS (Embedded Cluster)

For customers without an existing Kubernetes cluster, KOTS Embedded Cluster
ships a single-binary installer that brings up k0s and OMNIX in one step:

```bash
./omnix-installer  # ~30 minutes from clean VM to ready
```

## Audit evidence mapping

- **DORA evidence support** — replication actions can emit ML-DSA-65 signed
  receipts; the optional private Rekor instance can provide immutable
  retention.
- **EU AI Act Article 12 support** — gate transitions and receipt events create
  structured logging evidence for review.
- **EU AI Act Article 26(6) support** — retention policy is implemented through
  the Receipt and JobEvent tables when configured by the operator.
- **PQC-readiness planning** — OMNIX receipts use ML-DSA-65 / FIPS 204.
- **Security/compliance programs** — external evidence systems can ingest the
  signed artifacts when configured for the customer environment.

This guide does not replace the buyer's legal, compliance, or control review.

## Private Rekor

Customers under regulated regimes (DORA Art 6, EU AI Act Art 12/26(6), CMMC
2.0, CNSA 2.0) cannot use the public sigstore.dev Rekor log — its FOUO/CUI
posture is unsuitable and the log lives outside the customer's
jurisdiction. The enterprise chart can deploy a private Rekor v2 StatefulSet
that runs in-cluster, alongside the air-gapped OMNIX install.

### When to enable

Enable `rekor.enabled=true` when:
- The customer is under a regulator-facing audit regime that requires an
  in-cluster or jurisdiction-controlled transparency log.
- The customer's auditors will inspect inclusion proofs as part of their
  reporting cycle and must be able to verify them offline.
- The OMNIX deployment is air-gapped or otherwise unable to reach
  `rekor.sigstore.dev`.

### Storage sizing

- Default `rekor.storage.size: 50Gi` handles roughly 10M receipts at ~5KB
  each (with overhead).
- For higher-volume tenants, bump to 200Gi and switch to a fast SSD
  storageClass (`io1`, `gp3`, NVMe-backed).
- Trillian's MySQL backend defaults to a 20Gi PVC; for production, point
  `rekor.trillian.externalMysql.host` at an operator-managed MySQL cluster
  (Aurora, RDS, CloudSQL) and the in-cluster MySQL StatefulSet is omitted.

### Signing key onboarding

The Rekor server's identity is an ECDSA P-256 signing key, distinct from
the per-receipt ML-DSA-65 keys OMNIX uses. The operator mints it once
during pilot setup:

```bash
python -m omnix.cloud.sigstore.onboarding init \
    --rekor-url https://omnix-rekor.example.com:3000 \
    --namespace omnix
```

The command prints a Kubernetes Secret manifest. Apply it before
`helm upgrade rekor.enabled=true`.

### Audit-kit embedding

When `rekor.enabled=true`, every receipt OMNIX produces is submitted to the
in-cluster Rekor and the resulting inclusion proof is bundled into the
customer audit kit under `rekor/<receipt-id>.proof.json`. The kit's offline
`verify.py` verifies both the ML-DSA-65 receipt signature and the
inclusion-proof Merkle path. The Rekor server's public-key fingerprint
(SHA-256 of the DER) is embedded in the kit so the auditor can detect
tampering of the kit itself.

### HA upgrade path

The current chart deploys one Rekor StatefulSet replica and one in-cluster
MySQL StatefulSet replica. HA requires a chart change before documenting a
multi-replica `rekor` value.

For production planning, provision external MySQL (Aurora multi-AZ, RDS, or an
on-prem cluster) and set `rekor.trillian.externalMysql.host`; the in-cluster
MySQL StatefulSet is omitted automatically.

Schema migration between Rekor versions is handled by Trillian's standard
upgrade path; consult the Sigstore Rekor docs before any major upgrade.
