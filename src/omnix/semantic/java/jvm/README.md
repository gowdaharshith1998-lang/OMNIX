# `javaparser-emitter` — vendored JAR build & policy

This directory holds the JavaParser-based semantic emitter that backs
`omnix.semantic.java.parser.parse_file`. The Python side spawns a short-lived
JVM subprocess per source file and reads JSON-on-stdout matching the
`SemanticNode` schema.

## Why JavaParser (not Spoon)

| Concern             | JavaParser                              | Spoon                                  |
|---------------------|-----------------------------------------|----------------------------------------|
| Footprint           | ~3-4 MB shaded                          | ~15 MB + transitive deps               |
| Symbol resolution   | `symbol-solver-core` covers our needs   | Powerful but heavier model             |
| Transformation API  | Not needed — LLM does the rewrite       | Spoon's strength, dead weight for us   |
| Java 6 ↔ Java 21    | Both fine                               | Both fine                              |

OMNIX never rewrites Java in-process — the LLM does. We need *resolved types
and call edges*, nothing more. JavaParser + `symbol-solver-core` is the
smallest tool that satisfies the spec.

## Why subprocess + JSON-on-stdout (not JNI / gRPC)

- Matches `_run_verify_limited`'s isolation pattern (subprocess per file).
- No new IPC surface for AXIOM provenance to reason about.
- v1 throughput is fine: a few hundred files per project, JVM startup
  amortizes well against parse time. Daemonize later **only** if perf demands.
- Subprocess crashes do not corrupt orchestrator state.

## Required dependencies

The repository currently pins the JavaParser stack in `vendor/SHA256SUMS`:

| Artifact | Version | Purpose |
|---|---:|---|
| `com.github.javaparser:javaparser-core` | `3.26.3` | AST parsing |
| `com.github.javaparser:javaparser-symbol-solver-core` | `3.26.3` | Type and call resolution |
| `org.javassist:javassist` | `3.30.2-GA` | Symbol-solver runtime dependency |

Bumping any version is a separate slice because it can shift resolution
semantics.

## Build

The vendored JARs and the compiled emitter JAR ship in `vendor/`. To rebuild:

```bash
bash src/omnix/semantic/java/jvm/build.sh
```

`build.sh` is idempotent + reproducible:

1. Re-downloads the three upstream JARs from Maven Central.
2. Verifies each against the repo-pinned `SHA256SUMS` (cryptographic trust root)
   and the upstream `.sha1` sidecar (transport-integrity probe).
3. Compiles `JavaSemanticEmitter.java` against the vendored classpath.
4. Packages `javaparser-emitter.jar` with a `Class-Path` manifest and a fixed
   `--date=2026-01-01T00:00:00Z` so the JAR's SHA256 is byte-stable across
   machines and clocks. Two consecutive runs produce identical hashes.
5. Smoke-tests the emitter by parsing a trivial Java source and asserting
   the expected `SemanticNode` JSON shape.

Exits non-zero on any failure. The CI test `tests/semantic/java/test_vendor_integrity.py`
re-hashes the vendored JARs on every pytest run, so a JAR byte change without
a matching `SHA256SUMS` update fails CI loudly.

## Vendor location (now versioned)

```
src/omnix/semantic/java/vendor/javaparser-core-3.26.3.jar
src/omnix/semantic/java/vendor/javaparser-symbol-solver-core-3.26.3.jar
src/omnix/semantic/java/vendor/javassist-3.30.2-GA.jar
src/omnix/semantic/java/vendor/javaparser-emitter.jar
src/omnix/semantic/java/vendor/SHA256SUMS              # one line per JAR
```

All four JARs are checked into git (~2.7 MB total). Bumping any version is a
separate slice — it can shift symbol-resolution semantics. Always re-verify
SHA256SUMS in CI on rebuild.

## JVM lifecycle

- **v1 (now):** one `java -jar javaparser-emitter.jar <file> <cp...>` per
  source file. Wall-clock budget `30.0s` (overridable via `parse_file`'s
  `timeout_s`).
- **v2 (only if perf demands):** daemonize behind a Unix-domain socket protocol.
  Until measurements force the issue, we do not pay the complexity tax.

## Error protocol (must match `parser.py`)

| Exit | stderr                                                       | Python side                                |
|------|--------------------------------------------------------------|--------------------------------------------|
| 0    | (empty)                                                      | `list[SemanticNode]`                       |
| 1    | freeform stack trace                                         | `JavaSemanticError(stderr)`                |
| 2    | `UnresolvedSymbol: <symbol>@<file>:<line> :: <message>`      | `UnresolvedSymbolError(...)`               |
| —    | (subprocess wall-clock exceeded)                             | `JavaSemanticTimeoutError(path, t, stderr)`|

Silent fallback to `Object`-typed nodes is forbidden — it poisons gate logic.

## Coupling rules

- `omnix.semantic.java` MUST NOT import from `omnix.fabric`,
  `omnix.providers`, or `omnix.studio`. The semantic layer is downstream-only
  from a dependency standpoint.
- The emitter MUST NOT reach over the network. All inputs come in on argv.
