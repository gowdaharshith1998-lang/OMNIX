# OMNIX air-gapped deployment guide (Shape B)

This guide installs OMNIX into a customer-controlled Kubernetes cluster with no
internet egress.

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
omnix verify --bundle omnix-airgap-<version>.airgap
```

The bundle signature is ML-DSA-65 (FIPS 204). The verifier runs entirely
offline using the public key shipped inside the bundle's signed manifest.

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

## Compliance mapping

- **DORA Article 6** — every replication action emits an ML-DSA-65 signed
  receipt; the optional private Rekor instance provides 5-year immutable
  retention.
- **EU AI Act Article 12** — automatic, tamper-resistant logging of
  high-risk-AI events (every gate transition is signed and persisted).
- **EU AI Act Article 26(6)** — 6-month minimum log retention enforced by
  the Receipt + JobEvent table retention policy.
- **NIST PQC 2030** — ML-DSA-65 satisfies FIPS 204.
- **CNSA 2.0 (2035)** — same algorithm satisfies CNSA 2.0.
- **SOC 2 CC7.2 + CC4.1** — Drata integration auto-pushes evidence.

See `docs/compliance/` (Phase B4) for the full mapping.
