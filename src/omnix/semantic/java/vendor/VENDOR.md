# Vendored Dependencies — JavaParser stack

OMNIX vendors the JavaParser stack as JAR binaries so the M1 semantic layer
runs without a network fetch, a Maven/Gradle install, or a build-tool
sub-shell. The Python bridge in `src/omnix/semantic/java/parser.py` invokes
`java -jar javaparser-emitter.jar` as a short-lived subprocess.

## Provenance

| JAR | Maven Coordinate | Version | License |
|---|---|---|---|
| `javaparser-core-3.26.3.jar` | `com.github.javaparser:javaparser-core` | `3.26.3` | Apache License 2.0 |
| `javaparser-symbol-solver-core-3.26.3.jar` | `com.github.javaparser:javaparser-symbol-solver-core` | `3.26.3` | Apache License 2.0 |
| `javassist-3.30.2-GA.jar` | `org.javassist:javassist` | `3.30.2-GA` | Apache License 2.0 (also MPL 1.1 / LGPL 2.1; we elect Apache 2.0) |
| `javaparser-emitter.jar` | (locally built — see below) | from `JavaSemanticEmitter.java` in `../jvm/` | OMNIX source — `LICENSE` at repo root |

Upstream sources:
- https://github.com/javaparser/javaparser
- https://www.javassist.org/

All upstream JARs were retrieved from Maven Central (`https://repo1.maven.org/maven2`).
The locally built `javaparser-emitter.jar` is compiled from
`../jvm/JavaSemanticEmitter.java` against the three upstream JARs as classpath.

## Integrity gate

`SHA256SUMS` (sibling file) pins the SHA256 of every JAR. The CI test
`tests/semantic/java/test_vendor_integrity.py` re-hashes each JAR on every
run and fails hard on mismatch — a JAR byte change without a SHA256SUMS
update breaks CI loudly.

To verify locally:

```bash
cd src/omnix/semantic/java/vendor
sha256sum -c SHA256SUMS
```

## Rebuild (idempotent)

```bash
bash src/omnix/semantic/java/jvm/build.sh
```

The script: re-downloads upstream JARs to a temp dir, verifies their SHA256
against `SHA256SUMS` before moving into `vendor/`, compiles `JavaSemanticEmitter.java`
against the vendored classpath, packages the runnable JAR with a `Class-Path`
manifest, and runs a smoke parse on a trivial Java source to confirm the
build is functional. Exits non-zero on any failure.

## Update policy

To bump JavaParser (or javassist) versions:

1. Update the version constants at the top of `src/omnix/semantic/java/jvm/build.sh`.
2. Delete `SHA256SUMS` (the script regenerates it after verifying against the
   upstream-published `.sha256` sidecars).
3. Run `bash src/omnix/semantic/java/jvm/build.sh`.
4. Run `pytest tests/semantic/java/` — verify no behavioral regression.
5. Commit the bumped `SHA256SUMS` + bumped JARs in a single review-able commit.

A version bump is a **separate slice**. It can shift symbol-resolution
semantics; never bundle it with unrelated work.

## DO NOT

- Do not reshade or repackage upstream JARs. We use the upstream artifacts
  as published. Reshading multiplies our maintenance + license surface.
- Do not vendor multiple versions side-by-side. One version at a time.
- Do not modify JAR contents (no removing `META-INF`, no re-zipping).
  Modified JARs lose their upstream license attestation trail.
- Do not commit transient build output (`build/` dir, intermediate `.class`
  files) under `vendor/`. Only the four pinned JARs + `SHA256SUMS` + this file.
