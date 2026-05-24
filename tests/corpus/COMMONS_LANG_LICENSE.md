# Apache Commons Lang (vendored test-corpus subset)

OMNIX vendors a **trimmed subset** of Apache Commons Lang 2.6's
`org.apache.commons.lang.StringUtils` as a test corpus for the M1 rebuild
pipeline. Used only by tests — never linked, packaged, or redistributed as
part of any OMNIX product.

## Provenance

| Field | Value |
|---|---|
| Upstream artifact | `commons-lang:commons-lang:2.6` |
| Upstream source | `https://repo1.maven.org/maven2/commons-lang/commons-lang/2.6/commons-lang-2.6-sources.jar` |
| Full file size | 6594 lines / ~268 KB |
| Vendored | `tests/corpus/commons_lang/StringUtils.java` (trimmed — see below); full regression fixture at `tests/fixtures/java/commons-lang-2.6/src/main/java/org/apache/commons/lang/StringUtils.java` |
| License | Apache License 2.0 |
| Era | Java 6 (`org.apache.commons.lang` package — not `lang3`) |

## What was vendored

Only `org.apache.commons.lang.StringUtils.reverse(String str)` plus the
class header, package declaration, public constructor, and Apache 2.0
license header. The trimmed file is ~70 lines.

## What was changed

Exactly one substantive edit, documented inline in the file header:

- The original body of `reverse(String)` reads:
  ```java
  return new StrBuilder(str).reverse().toString();
  ```
  where `StrBuilder` is `org.apache.commons.lang.text.StrBuilder`.

- The trimmed body reads:
  ```java
  return new StringBuilder(str).reverse().toString();
  ```
  using `java.lang.StringBuilder` so the file is parseable in isolation
  by the OMNIX JavaParser-based symbol solver without vendoring the rest
  of Commons Lang (`StrBuilder`, `ArrayUtils`, etc.).

Functional contract is identical:

| Input | Original | Trimmed |
|---|---|---|
| `null`    | `null`  | `null` |
| `""`      | `""`    | `""` |
| `"bat"`   | `"tab"` | `"tab"` |

## Why trim instead of vendor the full file

The OMNIX semantic emitter is strict on symbol resolution per R-3.3 — every
referenced type must resolve via Reflection (java.lang.*), the source dir,
or supplied classpath JARs. The full 6594-line `StringUtils.java` references
~20 internal Commons Lang types (`StrBuilder`, `ArrayUtils`, `WordUtils`,
`Validate`, …). Vendoring all of them would bloat the test corpus by ~270 KB
and inflate the supply-chain surface for no test-value gain.

The M1 rebuild pipeline is verified end-to-end against this trimmed corpus.
Vendoring the full library is a future M2 concern (multi-file project
rebuild + transitive symbol resolution).

## License notice

Copyright Apache Software Foundation. Licensed under the Apache License,
Version 2.0. Full license:
`http://www.apache.org/licenses/LICENSE-2.0`

The Apache license header is preserved verbatim at the top of
`StringUtils.java`. The trim is documented in the file's class-level
JavaDoc. No author attribution was removed (the trimmed file references
"Apache Software Foundation" only — individual contributor `@author` tags
applied to deleted methods).

OMNIX vendors these files as test data only. They are not part of any
distributable artifact. The full fixture is retained specifically to guard
method-count and overload-indexing behavior; the trimmed corpus remains the
self-contained rebuild smoke fixture.
