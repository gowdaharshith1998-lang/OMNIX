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

As of 2026, both libs ship under group `com.github.javaparser` at the same
version — latest stable major is **3.x** (current `3.26.x` line). Pull the
matching pair:

| Artifact                                     | Purpose                              |
|----------------------------------------------|--------------------------------------|
| `com.github.javaparser:javaparser-core`      | AST parsing                          |
| `com.github.javaparser:javaparser-symbol-solver-core` | type / call resolution      |

Pinning the latest stable 3.x release in `vendor/SHA256SUMS` is mandatory.
Bumping the major is a separate slice (it can shift resolution semantics).

## Build

```bash
# 1. Fetch deps (e.g. via mvn dependency:get into a temp dir)
DEPS=/tmp/jp
mvn dependency:get -Dartifact=com.github.javaparser:javaparser-core:3.26.2 -Ddest=$DEPS
mvn dependency:get -Dartifact=com.github.javaparser:javaparser-symbol-solver-core:3.26.2 -Ddest=$DEPS

# 2. Compile against Java 21
javac --release 21 \
  -cp "$DEPS/javaparser-core-3.26.2.jar:$DEPS/javaparser-symbol-solver-core-3.26.2.jar" \
  JavaSemanticEmitter.java

# 3. Shade into a single executable JAR (preferred — no classpath gymnastics
#    on the Python side). Either use the maven-shade-plugin, or for the
#    quick path:
jar cfe javaparser-emitter.jar JavaSemanticEmitter *.class

# (If using the quick path, the runtime invocation becomes
#    `java -cp javaparser-emitter.jar:<deps> JavaSemanticEmitter ...`
#  Prefer the shaded variant so the Python bridge stays as simple as
#  `java -jar javaparser-emitter.jar ...`.)
```

## Vendor location

```
src/omnix/semantic/java/vendor/javaparser-emitter.jar
src/omnix/semantic/java/vendor/SHA256SUMS         # one line per JAR
```

`SHA256SUMS` format:

```
<sha256>  javaparser-emitter.jar
<sha256>  javaparser-core-3.26.2.jar     # if shipped alongside
<sha256>  javaparser-symbol-solver-core-3.26.2.jar
```

The `vendor/` directory is intentionally **not** in version control for this
slice. `scripts/vendor_javaparser.sh` (separate slice) will fetch, build,
verify, and place the artifacts.

## JVM lifecycle

- **v1 (now):** one `java -jar javaparser-emitter.jar <file> <cp...>` per
  source file. Wall-clock budget `30.0s` (overridable via `parse_file`'s
  `timeout_s`).
- **v2 (only if perf demands):** daemonize behind a unix-socket protocol.
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
