# M2 Live Run Protocol

This runbook is for the operator-run Phase 7 invocation. The coding agent
must not run the live LLM rebuild or spend provider budget.

## Corpus

The full Commons Lang 2.6 source fixture is vendored at:

```text
tests/corpus/commons_lang_full/org/apache/commons/lang/
```

`StringUtils.java` is the upstream 6594-line source file, with referenced
helper sources copied from `commons-lang-2.6-sources.jar` and converted to
UTF-8 for current Java tooling. Local parser verification currently emits
177 `org.apache.commons.lang.StringUtils.*` method/constructor nodes from
that upstream file. The dispatch target says 27 receipts; do not hide this
count mismatch in a demo. Confirm the intended 27-method manifest before
spending live LLM budget, or record the actual module count honestly.

## Dry Run Checks

From the OMNIX repo:

```bash
pytest tests/corpus/test_commons_lang_corpus.py tests/rebuild/test_cli.py -q
```

Expected:

```text
full StringUtils source exists at 6594 lines
full StringUtils parses without unresolved symbols
rebuild --module maps to org.apache.commons.lang.StringUtils.*
```

## Operator Live Project

Prepare a clean project outside the repo:

```bash
mkdir -p ~/omnix-m2-demo/src
cp -R ~/omnix/tests/corpus/commons_lang_full/org ~/omnix-m2-demo/src/
cd ~/omnix-m2-demo
omnix axiom keygen --project .
```

Register the provider key through the existing Vault UI flow. Do not store
keys in the repo, shell history, docs, casts, or receipts.

Analyze the project with the existing OMNIX analyze flow, then run:

```bash
time omnix rebuild . --target java21 --module org.apache.commons.lang.StringUtils
```

Verify receipts:

```bash
find .omnix/receipts/rebuilds -name '*.json' | sort | wc -l
for r in .omnix/receipts/rebuilds/*/*.json; do
  omnix axiom verify-rebuild "$r" --json
done | jq -s '{verified: map(.verified) | unique, summaries: map(.gates_summary)}'
```

For Phase 8, copy one clean passed receipt and one instructive Gate 6 failed
receipt back into `docs/` as:

```text
docs/m2_demo_receipt_sample_passed.json
docs/m2_demo_receipt_sample_failed.json
```

Do not commit cost-dollar fields. Token counts are acceptable.
