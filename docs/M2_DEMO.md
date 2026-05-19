# M2 Demo - Whole-module rebuild with signed receipts

Status: pending operator live run. Do not present this page as final until
`docs/m2_demo.cast`, `docs/m2_demo_receipt_sample_passed.json`, and
`docs/m2_demo_receipt_sample_failed.json` exist and pass:

```bash
python scripts/validate_m2_demo_assets.py .
```

## What the final cast must show

The Phase 8 cast is a single live `asciinema` take over the real Commons Lang
2.6 `org.apache.commons.lang.StringUtils` module. It must show:

1. `omnix rebuild` running with `--module org.apache.commons.lang.StringUtils`.
2. The receipt count printed by the CLI.
3. `omnix axiom verify-rebuild` returning `verified: true` for a passed receipt.
4. `omnix axiom verify-rebuild` returning `verified: true` for a receipt whose
   gate 6 status is `failed`.
5. The failed receipt's structured `diverging_input`.

The demo is credible only if the receipt set is the actual live-run output. Do
not replace the live receipt count with a hard-coded number, and do not edit the
cast.

## What gate 6 failed means

Gate 6 compares the legacy source and rebuilt source on the same generated probe
inputs. A gate 6 failure means OMNIX caught a real bug in the rebuilt behavior,
not OMNIX is broken. The signed receipt preserves that outcome instead of hiding
it or calling it a pass.

That is the M2 honesty point: a failed behavioral-equivalence gate is evidence
that the system found a semantic divergence. The useful artifact is the exact
receipt, including `details.diverging_input`, because it gives a developer the
input needed to reproduce and fix the mismatch.

## Reproduce

Follow [m2_live_run_protocol.md](m2_live_run_protocol.md) to prepare the clean
demo project and run the live rebuild. After the operator copies one passed and
one failed receipt sample into `docs/`, rehearse the final output with:

```bash
bash docs/m2_demo_rehearsal.sh
```

Record only after the rehearsal output is clean:

```bash
asciinema rec docs/m2_demo.cast \
  --idle-time-limit 2 \
  --command "bash docs/m2_demo_rehearsal.sh"
python scripts/validate_m2_demo_assets.py .
```

## What the receipts prove

The receipts prove that the JSON receipt bytes were signed by the project key,
the receipt hashes identify the legacy and rebuilt source bytes, and each gate
reported the status written into the receipt. They do not prove that skipped or
inconclusive gates passed. A gate must say `passed` to count as passed.

## Current caveat

The full upstream Commons Lang 2.6 `StringUtils.java` currently parses to 177
`org.apache.commons.lang.StringUtils.*` method and constructor nodes in OMNIX.
The dispatch target says 27 receipts. Resolve that count mismatch before
spending live LLM budget or recording the final cast.
