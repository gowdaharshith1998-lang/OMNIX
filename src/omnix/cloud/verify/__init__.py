"""Layer 5 verifier stack — the Pollux equivalent.

Four verifiers active simultaneously:
  1. Hypothesis property-based tests (already in OMNIX core / M2)
  2. GitHub Scientist port — in-process dual-run
  3. Diffy-style proxy — service-boundary diff with noise filter
  4. Daikon-lite invariant miner — re-mine on candidate, compare

The cloud surface composes (does not modify) gate6_behavioral.py. The
``gate6_extended`` module bolts the three new verifiers on after the
existing gate has emitted its receipt.
"""
