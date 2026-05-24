# TC401P Gate 6 Diagnostic

Run inspected:
`tests/fixtures/cobol/nist/.omnix/runs/2026-05-24T011308432Z-4515e8f8/`

Program state:
`TC401P gate6_failed`, `gate6_attempts=2`

Gate 6 stdout diff:

```text
expected:  "TOTAL=  $105,250.00 \n"
candidate: "TOTAL=   $105,250.00 \n"
                    ^
```

The candidate inserted one extra space before the dollar sign.

COBOL source evidence:

```cobol
01 DISPLAY-AMT  PIC $$,$$$,$$9.99-.
*> The edited picture output for this fixture is exactly two spaces after "=":
*> TOTAL=  $105,250.00 
DISPLAY "TOTAL=" DISPLAY-AMT.
```

M0 baseline Python emits:

```python
result = f"TOTAL=  {display_amt} "
return result.encode() + b"\n"
```

GraphRAG-enabled run inspected:
`tests/fixtures/cobol/nist/.omnix/runs/2026-05-24T011615702Z-b0c62b38/`

Outcome:
`verified=6 gate6_failed=0 errored=0`, including TC401P.

Root cause classification:
model-quality / nondeterministic no-graphrag live rebuild behavior for COBOL edited-picture spacing. The M0 hardening commit added the TC401P fixture comment specifically because Gate 6 had caught edited-picture spacing drift. The current source still has that comment, and `src/omnix/rebuild/cobol_runner.py` shows the prompt template was introduced in the M0 commit and not subsequently refined. The no-graphrag live model still missed the exact two-space requirement on this run.

Decision:
document TC401P as a known no-graphrag Python byte-compat exception. Do not modify Gate 6, receipt schema, or the locked rebuild algorithm body. Keep GraphRAG path as the verified route for this fixture.
