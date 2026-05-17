# XFAIL Audit — M1 Finisher Phase 3 Bookkeeping

Greppable, one-row-per-xfail bookkeeping for every `@pytest.mark.xfail` /
`pytestmark = pytest.mark.xfail` marker in `tests/`. Each row maps the
marker to which **future work stream** will flip it.

Two work streams are active:

- **M1 finisher Phase 4-7** — the mega-dispatch tracked in `TODOS_M1_FINISHER.md`
  (Phase 4: real LLM dispatch, Phase 5: emitter follow-up + Commons Lang
  corpus + GraphStore `rebuild_attempts`, Phase 6: signed receipt, Phase 7:
  demo recording).
- **slice 15.3.7** — pre-M1 backend work tracked in `TODOS.md` P1: provider
  error detail, LLM tool-dispatch, GraphStore locking, studio
  `/action/dispatch` route.

A marker that points at slice 15.3.7 will NOT flip during M1 finisher
Phases 4-7. That's by design — different layer, different work stream.

## Audit

| Marker location | Strict? | Future flip | Layer |
|---|---|---|---|
| `tests/gates/test_gate1_syntactic.py:103` | strict | M1 Phase 5 (emitter follow-up) | gates ↔ emitter |
| `tests/gates/test_gate1_syntactic.py:118` | strict | M1 Phase 5 (test-rewrite housekeeping alongside emitter slice) | test fixture |
| `tests/gates/test_gate2_typecheck.py:68` | strict | M1 Phase 5 (emitter body-type resolution) | gates ↔ emitter |
| `tests/gates/test_gate2_typecheck.py:88` | strict | M1 Phase 5 (emitter body-type resolution) | gates ↔ emitter |
| `tests/gates/test_gate3_signature.py:144` | strict | M1 Phase 5 (gate3 ↔ parse_file wiring) | gates ↔ emitter |
| `tests/fabric/test_provider_error_detail.py:12` (module) | strict | slice 15.3.7 provider error detail | fabric |
| `tests/fabric/test_real_tool_use.py:33` | strict | slice 15.3.7 tool-dispatch tools-param | fabric |
| `tests/fabric/test_real_tool_use.py:50` | strict | slice 15.3.7 tool-dispatch `_tool_use_message_list` | fabric |
| `tests/fabric/test_dispatcher_provider_override.py:14` (constant) | strict | slice 15.3.7 dispatch `provider_override` kwarg | fabric |
| `tests/graph/test_store_locking.py:16` | strict | slice 15.3.7 `GraphStore.locked_connection()` | graph |
| `tests/graph/test_store_locking.py:44` | **non-strict** | slice 15.3.7 `GraphStore` RLock (flaky-under-load — intentional non-strict) | graph |
| `tests/graph/test_store_locking.py:72` | strict | slice 15.3.7 `GraphStore.locked_connection()` (nested) | graph |
| `tests/graph/test_store_locking.py:91` | strict | slice 15.3.7 `GraphStore._lock` attribute | graph |
| `tests/studio/test_action_dispatch_route.py:15` (module) | strict | slice 15.3.7 `/action/dispatch` backend | studio |

## Counts

- **13 markers** (each marker may apply to multiple tests via module-level
  `pytestmark` or shared constants).
- **5 M1-finisher Phase 5** — gates ↔ emitter wiring.
- **8 slice 15.3.7** — pre-M1 work, separate work stream.
- **0 phase-unassigned** — every marker has an explicit flip target.
- **1 non-strict** (intentionally — flaky-under-load behavior documented inline).
- **12 strict** — no silent XPASS allowed; tripwires fire if behavior fixes
  without the marker being removed.

## Phase-pointer grep

```bash
# All M1 Phase 5 markers
grep -rn "M1 Phase 5" tests/

# All slice 15.3.7 markers
grep -rn "slice 15.3.7" tests/

# Anything that says "follow-up slice" but doesn't pin a phase
grep -rn "follow-up slice" tests/ | grep -v "M1 Phase\|slice 15.3.7"
```

If the last grep produces output, an xfail has lost its phase pointer
during a future refactor — restore it.

## Don'ts

- Do not bulk-remove markers with `sed`. Each removal: read the test,
  run it, confirm it XPASSES under strict, then remove. The dispatch's
  R-3.3 invariant.
- Do not relax `strict=True` to `strict=False`. The non-strict outlier
  on `test_concurrent_writes_serialized` is grandfathered with explicit
  inline justification — do not add new non-strict markers.
- Do not skip a failing test with `@pytest.mark.skip` to "temporarily
  hide" it. Either it passes (remove the xfail) or it stays xfail with
  a phase pointer.
- Do not add new xfails without a phase pointer. The grep above MUST
  return zero results.
