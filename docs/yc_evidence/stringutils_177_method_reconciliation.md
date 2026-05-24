# StringUtils 177 Method Reconciliation

## Summary

OMNIX now persists the complete Apache Commons Lang 2.6 `StringUtils` method graph. The full source contains 177 method-like declarations: 176 `method_declaration` nodes and 1 `constructor_declaration` node.

One sentence: OMNIX emits the complete method graph. No allowlist.

## Source

The regression fixture is copied from the Apache Commons Lang 2.6 source artifact:

```text
https://repo1.maven.org/maven2/commons-lang/commons-lang/2.6/commons-lang-2.6-sources.jar
```

Fixture path:

```text
tests/fixtures/java/commons-lang-2.6/src/main/java/org/apache/commons/lang/StringUtils.java
```

## Counts

Empirical tree-sitter count:

```text
methods: 176
constructors: 1
total: 177
unique method names: 117
```

Current Java semantic parser before this fix:

```text
parse_file nodes: 177
unique semantic FQNs: 118
persisted graph nodes: 118
```

The current repo had already fixed the parser-side 27-node symptom. The remaining bug was graph persistence: overloaded methods shared the same semantic FQN, so `GraphStore.add_node(id=n.fqn, ...)` replaced earlier overloads with later overloads.

Post-fix graph persistence:

```text
parse_file nodes: 177
unique semantic FQNs: 118
persisted graph nodes: 177
```

## Predicate Removed

No visibility, deprecation, or allowlist predicate was present in the current code. The dropping predicate was implicit primary-key collapse in `src/omnix/orchestrator/graph_adapter.py`:

```python
store.add_node(id=n.fqn, ...)
```

That has been replaced by deterministic graph IDs. Non-overloaded methods keep their original FQN. Overloaded methods use the semantic FQN plus resolved parameter types, for example:

```text
org.apache.commons.lang.StringUtils.indexOf(java.lang.String,char)
org.apache.commons.lang.StringUtils.indexOf(java.lang.String,char,int)
org.apache.commons.lang.StringUtils.indexOf(java.lang.String,java.lang.String)
org.apache.commons.lang.StringUtils.indexOf(java.lang.String,java.lang.String,int)
```

The original name is retained in node metadata as `semantic_fqn`; metadata also records `signature`, `resolved_param_types`, `resolved_return_type`, `visibility`, and `deprecated`.

## OMNIX Self-Host Impact

Self-host impact artifacts were generated with:

```bash
python3 omnix.py impact populate_from_semantic_nodes --direction upstream --depth 3 --include-tests --json > /tmp/java_populate_upstream.json
python3 omnix.py impact populate_from_semantic_nodes --direction downstream --depth 3 --include-tests --json > /tmp/java_populate_downstream.json
```

Current OMNIX call-edge impact for `populate_from_semantic_nodes` reports no upstream or downstream `CALLS` edges. The behavioral graph delta is the persisted node delta: 118 before, 177 after, +59 overloaded method/constructor graph nodes preserved.

## Verification

```bash
python -m pytest tests/semantic/java/test_stringutils_count.py -q
python -m pytest tests/semantic/java tests/corpus/test_commons_lang_corpus.py tests/orchestrator/test_e2e_stringutils.py tests/orchestrator/test_dispatcher.py -q
ruff check src tests
mypy src/omnix
python -m pytest -q
tmpdir=$(mktemp -d /tmp/omnix-build.XXXXXX)
python -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install --upgrade pip build
"$tmpdir/venv/bin/python" -m build
python3 omnix.py analyze . --no-open --port 8801
python3 omnix.py detect-changes --scope worktree --json
```

Closeout results:

```text
focused regression: 1 passed
related Java/orchestrator suite: 36 passed
ruff: All checks passed
mypy: Success, no issues in 248 source files
full pytest: 950 passed, 6 skipped, 13 xfailed
package build: Successfully built omnix-0.6.1.tar.gz and omnix-0.6.1-py3-none-any.whl
self-host analyze receipt: /home/harsh/.omnix/receipts/analyze_2026-05-24T04-38-03Z_5f966b6.json
self-host receipt verification: Signature verified successfully
```
