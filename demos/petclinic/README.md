# OMNIX Live Demo: Spring Petclinic

Reproducible end-to-end demo showing OMNIX ingesting Spring Petclinic,
producing signed receipts, and exercising a 1% traffic shift through the
strangler-fig facade in about 15 minutes on a developer laptop.

## What this demo shows
1. OMNIX ingests a real public Java codebase (Spring Petclinic, ~5.5K LOC)
2. The graph builds; the spec mines; the six verification gates run
3. At least one unit emits a real ML-DSA-65 signed receipt
4. The signed receipt verifies offline against the published public key
5. A 1% traffic shift through the strangler-fig facade actually moves traffic

## Why Spring Petclinic
- Public, well-known reference codebase used by the Spring team itself
- Real production-shape Java (controllers, services, repositories, JPA)
- Small enough to scan in <5 minutes; large enough to be non-trivial
- No corporate IP concerns
- Pre-existing test suite (~80 tests) gives the property-based gate something to chew on

## Prerequisites
- A running kind cluster from the deploy verification dispatch
  (`.scratch/verify/<TS>/` exists, `omnix-verify` cluster reachable)
- `kubectl`, `helm`, `docker`, `gh`, `curl`, `jq`, `git`
- 5–10 minutes of attention; the demo is self-driving but you'll want to
  watch the Studio at `http://127.0.0.1:8080` during the run

If the kind cluster is not present, the script halts with a clear message
pointing you at the deploy verification dispatch.

## Run the demo
```bash
cd demos/petclinic
./demo.sh
```

## What the demo produces
Under `demos/petclinic/runs/<TS>/`:
- `petclinic.tar.gz` — the input codebase (cached at `demos/petclinic/cache/` for repeat runs)
- `job-events.json` — full gate-by-gate event log
- `receipts/*.json` — every signed receipt with payload + signature + pubkey
- `verify.txt` — offline-verify result per receipt
- `routes-before.json` / `routes-after-1pct.json` / `routes-after-rollback.json`
- `traffic-baseline.txt` / `traffic-after-shift.txt`
- `REPORT.md` — single-page summary of inputs, gate outcomes, receipts, and traffic-shift results

## Operator flow
1. Open the Studio in a browser tab BEFORE you run `./demo.sh`
2. Run `./demo.sh`
3. As the script announces each gate, the Studio's CHAT tab streams the gate events live
4. When the script announces "shift requested" — switch to the Studio's CutoverModal to show the receipt preview
5. When the script announces "verified offline" — show the verifier page at `/verify/r/<id>`

The whole thing is < 15 minutes from `./demo.sh` to "here's the signed receipt."

## Known limitations on a kind cluster
Some surfaces from the full live-observation deployment are not exercisable on
kind without additional setup (matching the deploy verification dispatch's
findings):

- **Tetragon eBPF observation:** kind nodes don't bundle the kernel modules
  Tetragon's kprobes require. Demo skips this; CDC + mainframe paths still
  work.
- **Rekor v2 transparency log:** Trillian MySQL bootstrap requires extra
  init that isn't in the chart yet (tracked separately).
- **Strangler-fig writer sidecar:** the writer runner module is an open
  follow-up (tracked in issue #45). The demo's traffic-shift step still
  exercises the controller's in-process shift; the per-pod sidecar
  rewrite of `routes.json` is a no-op until that follow-up lands.

These limitations do not affect the demo's core result: OMNIX scans real Java
and produces a signed receipt that can be verified offline.

## Caching
First run downloads Spring Petclinic from GitHub. Subsequent runs use the
cached tarball at `demos/petclinic/cache/petclinic.tar.gz` so the demo
stays under 5 minutes wall time.
