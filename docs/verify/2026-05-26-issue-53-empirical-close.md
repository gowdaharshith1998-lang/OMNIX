# Issue #53 — Empirical Close

Run timestamp: 2026-05-26
HEAD at end: `663c96e`

## Summary

Issue #53 is empirically closed. After PR #55 (CDS via filesystem + native sidecar + LOGICAL_DNS for candidates) and the two cluster-environment follow-ups (#56 Envoy admin bind, #57 stubs Service names), the strangler-fig data plane actually moves traffic on a real kind cluster.

## Empirical results

All three binomial confidence interval bounds held on a live kind cluster with the merged PR #55 image:

| Shift | Expected (99% CI) | Observed | Result |
|---|---|---|---|
| 25% × 200 | candidate ∈ [33, 67] | **54 candidate / 146 legacy** | ✅ PASS |
| 50% × 200 | candidate ∈ [81, 119] | **99 candidate / 101 legacy** | ✅ PASS |
| rollback × 100 | candidate ≤ 6 | **0 candidate / 100 legacy** | ✅ PASS |

Before this work (verify dispatch 2026-05-26 Phase D, evidence under `.scratch/verify/20260526T020219Z/cutover/`): 200 requests → 200 empty responses, blocked by static-cluster mismatch (#53).

After PR #55: 200 requests → real binomially-distributed split, exactly within the expected interval.

## Chain verified end-to-end

1. `POST /v1/cutover/test/shift` (target_percentage=25) → 200 with ML-DSA-65 signed receipt.
2. Controller publishes to RedisStreamsCutoverBus (cross-worker).
3. SSE `/v1/cutover/events` delivers to `facade_writer_runner` sidecar.
4. Writer log: `applied shift tenant=int unit=test pct=25`.
5. Writer atomically rewrites BOTH:
   - `/etc/envoy/clusters/clusters.json` — defines `legacy_test` (STRICT_DNS → `legacy.omnix-int.svc:80`) + `candidate_test` (LOGICAL_DNS → `omnix-candidate-test.omnix-int.svc:80`).
   - `/etc/envoy/routes/routes.json` — weighted_clusters with names matching the clusters above.
6. Envoy filesystem CDS + RDS hot-reload (~1s mtime poll).
7. Production traffic splits at the configured ratio.

## Side fixes landed during verification

| PR | What |
|----|------|
| #56 | Envoy admin bind back to 0.0.0.0 so kubelet readinessProbe reaches it (PR #55 set 127.0.0.1, broke probe). |
| #57 | Integration stub Service names use DNS-1035 (`legacy` / `omnix-candidate-test`, not `legacy_test` / `candidate_test`). PR #47 typo. |

## Verdict

**Issue #53 is closed by evidence**, not just by argument. The strangler-fig stops being aspirational. Phase D of the verify dispatch returns binomial-CI-confident traffic distribution.

Open follow-ups (all LOW from the #55 pre-merge review):
- L1: integration tests mutate `SEED_RETRY_BACKOFFS` directly (safe under default pytest-asyncio sequential mode).
- L2: readinessProbe doesn't assert `cluster count > 0` — empty-but-valid CDS file lets the pod be Ready while every request 503s.
- L3: `r.json()` raises `json.JSONDecodeError` not caught in seed (init restart re-runs retry).
