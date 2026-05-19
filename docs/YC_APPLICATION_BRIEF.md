# YC Application Brief - M2 evidence draft

Status: draft pending Phase 8 live assets. This brief must be updated only after
`docs/m2_demo.cast` and the two sample receipts exist and validate with:

```bash
python scripts/validate_m2_demo_assets.py .
```

## Company

OMNIX builds migration tooling that records signed evidence for code rebuilds.
For each rebuilt method, the system emits a `RebuildReceipt` with source hashes,
model identity, prompt-template version, gate results, timestamp, and an Ed25519
signature.

## Problem

Large code migrations often leave reviewers with two weak options: trust a diff,
or rerun a partial test suite. Neither option gives a durable record of what was
checked, what was skipped, and what failed. Teams need migration artifacts that
can be audited after the run, not only during the run.

## What M2 demonstrates

M2 targets Apache Commons Lang 2.6 `StringUtils`. The intended live asset shows a
whole-module rebuild, signed receipt emission, offline receipt verification, and
one behavioral-equivalence failure preserved in the receipt. The failed gate is
not hidden. It records `diverging_input`, which gives the developer a concrete
reproduction input for the mismatch.

## Why this matters

The useful claim is narrow: OMNIX can attach verifiable evidence to a migration
attempt, including negative evidence. If a gate fails, the receipt says it
failed. If a gate is skipped or inconclusive, the receipt does not call it a
pass. That makes the artifact useful for engineering review because it separates
successful checks from unproven checks.

## Current status

Phases 2 through 7 are stacked in pull requests. The repo contains the full
Commons Lang source fixture, Gate 5 and Gate 6 receipt wiring, a module-prefix
CLI path, and a live-run protocol. The remaining Phase 8 work is an operator-run
live rebuild plus a single-take asciinema cast. The live run must resolve the
current count mismatch: the parser sees 177 `StringUtils` nodes while the
dispatch target expects 27 receipts.

## Reproducibility

After the operator run, the public artifact set should contain:

- `docs/m2_demo.cast`
- `docs/m2_demo_receipt_sample_passed.json`
- `docs/m2_demo_receipt_sample_failed.json`
- `docs/M2_DEMO.md`

The validator in `scripts/validate_m2_demo_assets.py` checks duration, required
cast output, absence of obvious secret patterns, sample receipt gate 6 status,
and unsupported public-language phrases.
