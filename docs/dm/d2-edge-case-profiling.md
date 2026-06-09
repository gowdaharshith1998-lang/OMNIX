# D2 — AI Edge-Case Profiling (Implementation Notes)

## Status

D2 is available as a DM library surface. It consumes the D1 mapping manifest,
plans explicit probes, and emits a signed `edge-case-manifest.json` chained to
D1.

## EARS contract

> **When** D1 has emitted a valid `column-mapping.json`, the system **shall**
> (1) instantiate an EFE-minimising planner, (2) generate candidate probes
> across 6 categories per mapping, (3) prioritise probes by EFE,
> (4) execute against legacy via parameterised SQL, (5) emit a signed
> `edge-case-manifest.json` chained to D1 via `predecessor_hash`.
>
> **When** any finding has `severity="blocker"` the manifest's
> `requires_operator_review` is `true`.

## Probe planner

`probe_planner.plan(mappings, schema, seed=0)`:

The planner treats each candidate probe as an action whose execution
updates the agent's posterior over the hidden state
`status ∈ {survives_d3, blocker, unknown}` for a given mapping. It selects
actions by minimising **expected free energy** (Friston 2017):

```
EFE(a) = - epistemic_value(a) - pragmatic_value(a)
```

* *epistemic value* ≈ entropy reduction (info gain).
* *pragmatic value* ≈ alignment with preference for `survives_d3`.

The implementation is deterministic given a seed and computes EFE
directly per (mapping × probe-category) pair — a full pymdp `Agent` is
unnecessary for this three-state space. Every mapping is either probed or
explicitly excluded with recorded rationale.

## Six probers

| Probe | What it detects | Severity floor |
|---|---|---|
| `null_distribution` | NULLs in NOT-NULL columns; nontrivial null rates | blocker / info |
| `encoding_anomaly` | non-UTF8 bytes, mojibake, control chars | blocker / warn |
| `orphan_fk` | rows with FK pointing at missing parent | blocker |
| `timezone_drift` | source-naive vs target-TZ-aware; midnight clustering | blocker / warn |
| `precision_boundary` | source MAX(ABS) exceeds target precision; scale truncation | blocker / warn |
| `sentinel_value` | 1900-01-01, -1, 'N/A', etc above 1% of rows | warn |

Each prober:

* Uses parameterised SQL exclusively. Identifiers go through
  `quote_ident()` which rejects any quote character. Sentinel literals
  go through `_safe_literal()` which rejects single-quote/newline/null.
* Has a 10-second wall-clock + statement-timeout budget. Timeouts and
  errors are surfaced as `status='timeout'/'error'` — never swallowed.
* Has a non-empty `remediation_hint` on every finding so the D3 transformation
  synthesis phase knows what to do.

## Manifest emit

`manifest_emitter.emit(...)`:

* Requires a non-empty `predecessor_hash` (must chain to D1).
* Aggregates findings + computes stats (blocker/warn/info, timeout/error).
* `requires_operator_review` is `true` iff any blocker or any
  `requires_human_decision` finding exists.
* Probe failures are first-class — they go into `probe_failures` rather
  than being silently dropped from the `findings` array.
* Sign-then-emit-both atomic write semantics.
