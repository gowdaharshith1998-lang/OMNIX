# OMNIX Self-Host CLI M3.5.2

M3.5.2 exposes OMNIX's own graph index as the default agent safety surface. The new commands wrap existing primitives: SQLite graph nodes and `CALLS` edges, per-file hash metadata, Git diff scope detection, and ML-DSA-65 receipt signing.

## Commands

```bash
omnix status
omnix impact <symbol> --direction upstream --depth 3 --include-tests
omnix detect-changes --scope staged
omnix analyze . --no-open
```

`omnix status` reports indexed commit, current commit, graph size, and the latest analyze receipt.

`omnix impact` walks `CALLS` edges upstream, downstream, or both from a symbol. It accepts bare names such as `_text`, graph ids such as `src/omnix/parser/python_parser.py::_text`, or `file.py:symbol`.

`omnix detect-changes` reports staged, worktree, or full drift files and annotates each changed path with node and edge counts from `omnix.db`.

`omnix analyze` now performs the graph refresh before Studio starts, stamps `indexed_commit` / `indexed_at` in `.omnix/omnix.db`, writes `~/.omnix/receipts/analyze_<timestamp>_<commit>.json`, and signs it when `~/.omnix/keys/secret.pem` exists.

## Verification

```bash
python -m pytest tests/cli -q
python3 omnix.py status
python3 omnix.py impact _text --direction upstream --depth 2 --json
python3 omnix.py detect-changes --scope worktree
LATEST=$(ls -t ~/.omnix/receipts/analyze_*.json | head -1)
SIG="${LATEST%.json}.sig"
python3 omnix.py axiom verify "$LATEST" "$SIG" --pubkey ~/.omnix/keys/public.pem
```

The first self-host receipt for this branch is copied to:

```bash
docs/yc_evidence/omnix_self_host_5f966b6.json
docs/yc_evidence/omnix_self_host_5f966b6.json.sig
```

## Locked Architecture Compliance

M3.5.2 does not modify the COBOL runner, Gate 6 behavioral gate, COBOL receipt schema, locked COBOL demo receipt directory, Studio frontend, find-bugs scan pipeline, or fabric dispatcher. The change is additive CLI wrapping around existing graph, Git, and signing primitives.
