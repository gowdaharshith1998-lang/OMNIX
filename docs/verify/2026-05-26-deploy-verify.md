# OMNIX Deploy Verification Report — 2026-05-26

Run timestamp: `20260526T020219Z`
Branch: `main`
HEAD at start: `f791ae8` (PR #47 mega-dispatch)
HEAD at end: `55a1721` (after fix PRs #48/49/50/51/52)

## Summary

End-to-end verification of the OMNIX chart + cloud surface on a real kind cluster. Five fix PRs landed during the run, each closing a distinct verification gap. The full strangler-fig control-plane chain (controller → bus → SSE → writer → routes.json) works end-to-end on a real cluster; one chart-design issue (#53) blocks actual Envoy traffic routing pending a separate refactor.

## Phase A — Local sanity ✅
- pytest cloud:    **261 passed**
- pytest repo:     **925 passed** (3 skipped, 27 xfailed)
- helm lint:       parent + mainframe subchart clean
- render baseline: 21,321 lines, 49 Kinds (Cluster, CRDs, Deployments, Services, ConfigMaps, NetworkPolicies, HPAs, PDBs, Ingress, Secrets, ServiceAccounts, MutatingWebhookConfiguration, ValidatingWebhookConfiguration, PVC, Pod)
- render maximalist: 22,249 lines, 70 Kinds (+ DaemonSet for Tetragon, Jobs for Rekor init, StatefulSets, TracingPolicy)
- locked-paths diff: **empty**

## Phase B — Live cluster ✅
- kind cluster:    omnix-verify control-plane Ready
- docker build:    omnix-cloud-api:verify (276MB)
- kind load:       success after docker.io/library/ tagging
- helm install:    succeeded with subcharts off + legacy DSN + memory storage backend
- All-pods-Ready:  api + worker + redis (side) + facade + legacy + candidate

## Phase C — End-to-end smoke ✅ **THE MONEYSHOT**
- API health:      200 OK
- /v1/cutover/units (PR #47 endpoint): 200 OK, [] empty
- POST /v1/jobs (inline + production):
  - job_id allocated: `f5b758ba65c34ad6a389844098984949`
  - state: `awaiting_cutover`
  - 1 receipt returned: `rcpt-inline-f5b758ba65c34ad6a389844098984949`
- **Offline ML-DSA-65 verify: PASS** (pk=1952B, sig=3309B — spec-correct FIPS 204)
- The "real cluster produces signed receipts that verify offline" line is now demonstrated.

## Phase D — Cutover smoke ⚠️ partial
- baseline traffic: "no healthy upstream" (expected — Envoy boots with empty routes)
- POST shift 25%:  200 OK, signed receipt
- Writer log:      `applied shift tenant=verify unit=calculator pct=25` ✅
- routes.json on facade Pod:
  - vhost domains: `['calculator', 'calculator.svc']` ✅
  - legacy_calculator weight=75 ✅
  - omnix-candidate-calculator.omnix.svc.cluster.local:80 weight=25 ✅
- **Control plane chain proven end-to-end on real cluster.**
- ❌ Traffic sampling: 200/200 empty responses — blocked by [#53](https://github.com/gowdaharshith1998-lang/OMNIX/issues/53) (static Envoy cluster table doesn't match the per-unit cluster names the writer generates)

## Phase E — Triage + fix PRs

Five fix PRs landed during this run:

| PR | Title | What it closed |
|----|-------|----------------|
| [#48](https://github.com/gowdaharshith1998-lang/OMNIX/pull/48) | sse-starlette in cloud extras | api Pod ImportError on every install |
| [#49](https://github.com/gowdaharshith1998-lang/OMNIX/pull/49) | postgres Cluster CRD post-install hook | CNPG ships CRDs as templates → Cluster manifest rejected at admission |
| [#50](https://github.com/gowdaharshith1998-lang/OMNIX/pull/50) | env-driven cutover bus | gunicorn --workers 2 → InMemoryBus split across workers |
| [#51](https://github.com/gowdaharshith1998-lang/OMNIX/pull/51) | bounded Redis publish | sync xadd hung worker → SIGABRT |
| [#52](https://github.com/gowdaharshith1998-lang/OMNIX/pull/52) | NetworkPolicy allowSameNamespace | side-deployed Redis blocked by app-only egress |

One follow-up issue filed:

- [#53](https://github.com/gowdaharshith1998-lang/OMNIX/issues/53) facade Envoy static clusters use literal `{unit}` — blocks per-unit traffic shifts. Requires CDS or writer-managed clusters.json (chart-design change beyond a verify-cycle fix).

## Conclusion

**Deployable on kind: PARTIAL.** The chart now installs cleanly, the api/worker/facade reach Ready, signed receipts round-trip end-to-end on a real cluster, and the strangler-fig control-plane chain (POST shift → bus → SSE → writer → routes.json) is verifiably working. Traffic actually routing through Envoy per the shift is blocked by #53 — a chart-design refactor, not a runtime bug.

**Next operator action:** Resolve #53 (CDS or writer-managed clusters.json). Then re-run Phase D — the rest of the chain is proven.

## Evidence

Full artifact set under `.scratch/verify/20260526T020219Z/` (2.7MB, 40 files). Not committed — `.scratch/` is in `.gitignore`.
