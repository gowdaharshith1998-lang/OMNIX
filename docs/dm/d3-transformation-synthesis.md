# D3 — AI Transformation Synthesis (PR B)

> Pipeline walkthrough + security model + grounded Reflexion explainer for
> `omnix.dm.d3_transformation_synthesis`.

## What D3 delivers

For every `ColumnMapping` produced by D1 (PR A), augmented with every blocker
`AnomalyFinding` produced by D2 (PR A), D3 emits a signed `TransformerSpec`
receipt containing:

* A Python `def transform(v: SourceType) -> TargetType` source string, verified
  by Hypothesis property tests derived from the D2 blocker manifest.
* (Optional) an equivalent SQL `CASE` expression for DB-side bulk import.
* (Optional) an equivalent Datalog rule for cross-model migrations (per
  Dynamite, PVLDB 2020).

If five Reflexion iterations cannot produce a transformer that passes every
property, D3 emits a `transformer-halt-<key>.json` receipt instead. **There
is no path that produces a `Success` receipt with a failing property** — the
schema enforces `properties_failed: maxItems: 0`.

## Pipeline

```
PR A signed manifests                D3 pipeline                    PR B signed receipts
─────────────────────                ───────────                    ─────────────────────
column-mapping.json   ┐                                              transformer-spec-<key>.json
                      ├── consumer.py ──┐                                 + .sig + .chainhash
edge-case-manifest.json                 │
                                        ↓
                            property_generator.py
                                        │
                                        ↓
                                    cegis.py
                                        │
                                        ↓                            transformer-halt-<key>.json
                            llm_synthesizer.py  ──→ Claude API           + .sig + .chainhash
                                        │       (mockable in CI)
                                        ↓
                            transformer_dsl.py
                            (RestrictedPython + subprocess fence)
                                        │
                                        ↓
                            reflexion_loop.py
                            (max 5 iterations, MFI monotone)
                                        │
                                        ↓
                            sql_tier.py / datalog_tier.py
                                        │
                                        ↓
                            spec_emitter.py / halt_report.py
                                        │
                                        ↓
                            ML-DSA-65 signed receipt
                            (predecessor_hash chains to D2)
```

## Grounded Reflexion (post Huang ICLR 2024)

Reflexion (Shinn et al., NeurIPS 2023) showed 91% pass@1 on HumanEval with
verbal self-critique. But Huang et al. ICLR 2024 demonstrated that pure
*intrinsic* self-correction is fragile: the model invents plausible-sounding
wrong critiques and degrades correct answers.

D3's escape: **the critique is never LLM-generated**. It is the Hypothesis
*minimum failing input* — a concrete value the transformer produced wrong
output for, with concrete expected vs actual. The LLM sees:

```
FAILED PROPERTY: preserves_timezone
INPUT:        datetime(1900, 1, 1, 0, 0, 0)
YOUR_OUTPUT:  datetime(1900, 1, 1, 0, 0, 0)  # tzinfo dropped
EXPECTED:     datetime(1900, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
HINT: target column is TIMESTAMP WITH TIME ZONE; you must preserve tzinfo.
```

This is the Property-Generated Solver (arXiv 2506.18315) pattern that
measured 23.1–37.3% pass@1 over standard TDD.

**Safeguards on top of grounding:**

1. **Monotone MFI history.** Each iteration appends; nothing ever drops.
2. **BACE-style anchor** (GECCO 2026). The D2 blocker manifest is the
   immutable "anchor" — tests are derived from blockers, not LLM-generated.

## Security model — three concentric defenses

LLM-emitted Python is **hostile input**. The CVE-2026-40217 (LiteLLM, May
2026) lesson: custom regex sandboxes are bypassable; AST-level rewriting is
the floor.

| Layer | Mechanism | What it blocks |
| --- | --- | --- |
| 1 | Strict AST allowlist in `transformer_dsl.validate_ast` | Import, ClassDef, Try, For, While, Yield, With, async, dunder attribute access, calls to anything outside `ALLOWED_CALLS` |
| 2 | RestrictedPython 8.1 `compile_restricted` | `a.b` rewritten to `_getattr_(a, "b")` which refuses dunders at runtime; safe builtins dict; no `open`/`eval`/`exec`/`__import__` |
| 3 | Subprocess fence via `sandbox_runner.py` | `RLIMIT_CPU=5s` (SIGXCPU → ExecutionTimeout), `RLIMIT_AS=256MB` (SIGKILL → ExecutionOOM), `RLIMIT_NOFILE=8`. New process group so the parent can kill the entire subtree on timeout. |

**Pen-tested escape patterns** (10+ in `test_transformer_dsl.py`):

* `__import__('os').system(...)` — blocked at AST allowlist
* `().__class__.__bases__[0].__subclasses__()` — dunder attribute access blocked
* `(0).__class__.__mro__[1]` — dunder blocked
* `(lambda: None).__globals__` — dunder blocked
* `open('/etc/passwd').read()` — `open` not in `ALLOWED_CALLS`
* `f"{v.__class__}"` (format-string escape) — dunder in AST
* `getattr(__builtins__, 'eval')` — `getattr` not in `ALLOWED_CALLS`
* `(lambda: 0).__code__.co_consts` — dunder blocked
* `''.__class__.__bases__[0].__subclasses__()[40]('cat /etc/passwd', shell=True)` — dunder blocked

**Prompt-injection containment.** All legacy sample values are
`json.dumps`-serialized into the user prompt. The system prompt explicitly
labels `SAMPLE_VALUES` as opaque data the model must not interpret as
instructions. Injected payloads containing fence-opener strings are escaped
into the JSON quoted string and cannot create a real Markdown fence.

## SketchLibrary (Migrator CEGIS)

`cegis.SKETCHES` is a 15-element tuple of `SketchHint` records. Each sketch
declares a `type_pair` (e.g., `("DATE", "TIMESTAMP_TZ")`), a Python
template, the blocker categories it applies to, and a `historical_pass_rate`.

`cegis.select_sketches` filters by `(legacy_norm, target_norm)`, excludes
any sketch in the pruned set, scores remaining sketches by
`historical_pass_rate + 0.05 * len(blocker_overlap)`, and returns the top-3.
The top sketch is fed into the LLM prompt as a hint; on iteration failure
its `sketch_id` is appended to `pruned_sketches`. The Reflexion loop will
not retry it.

`TransformerSpec.cegis_pruned_sketches` records the complete pruning
history per migration so operators can see which patterns the LLM tried and
which failed.

## Receipt schema

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `omnix-dm/transformer-spec/v1` | Const. |
| `migration_id` | string | Pattern `^[a-z0-9][a-z0-9-]*$`. |
| `predecessor_hash` | 64-char hex | Canonical SHA-256 of D2's `edge-case-manifest.json`. |
| `column_mapping_key` | string | `"{legacy_table}.{legacy_column}"`. |
| `python_source` | string | The accepted transformer body. |
| `sql_case` / `datalog_rule` | string or null | Optional tier outputs. |
| `properties_passed` | array of string | `minItems: 1`. |
| `properties_failed` | array of string | `maxItems: 0` (invariant — never non-empty for a Success). |
| `mfi_history` | array | All failing MFIs across iterations. |
| `iterations_used` | integer | `[1, 5]`. |
| `cegis_pruned_sketches` | array of string | |
| `tier_failures` | array | Each `{tier, reason, failing_mfi?}`. |
| `tier_chosen` | enum | `python` / `sql` / `datalog`. |
| `confidence` | number | `[0.0, 1.0]`. Degraded if low_confidence mapping or partial tier coverage. |
| `requires_operator_review` | boolean | True for `low_confidence`/`ambiguous` mappings. |
| `bisimulation_placeholder` | object | Reserved for PR E (Z3 TRA proof). |

## Honest gaps deferred

* **Live Claude API not hit in CI.** Mocked by default; operator runs with
  `OMNIX_DM_RUN_INTEGRATION=1` + `ANTHROPIC_API_KEY` for the live variant.
* **No bulk import / no CDC.** D3 emits transformer *specifications*. PR C
  applies them.
* **No exhaustive row diff.** PR D's `D4` will hit every row.
* **No formal bisimulation proof.** PR E's `D5` will discharge the bounded
  proof and fill `bisimulation_placeholder`.
* **SQL tier verification skipped without a transient PG container.** When
  the verifier cannot reach a database, `TierFailure(reason="infrastructure_unavailable")`
  is recorded honestly — no false success.
