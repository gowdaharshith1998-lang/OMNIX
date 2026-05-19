# Apache Commons Lang (vendored test corpora)

OMNIX vendors a **trimmed subset** of Apache Commons Lang 2.6's
`org.apache.commons.lang.StringUtils` as a test corpus for the M1 rebuild
pipeline, and a full Commons Lang 2.6 source tree subset rooted at
`org.apache.commons.lang` for the M2 whole-module demo scaffolding. Used
only by tests and demo fixtures — never linked, packaged, or redistributed
as part of any OMNIX product.

## Provenance

| Field | Value |
|---|---|
| Upstream artifact | `commons-lang:commons-lang:2.6` |
| Upstream source | `https://repo1.maven.org/maven2/commons-lang/commons-lang/2.6/commons-lang-2.6-sources.jar` |
| Full file size | 6594 lines / ~268 KB |
| Vendored | `tests/corpus/commons_lang/StringUtils.java` (trimmed — see below) |
| Vendored full corpus | `tests/corpus/commons_lang_full/org/apache/commons/lang/**` |
| License | Apache License 2.0 |
| Era | Java 6 (`org.apache.commons.lang` package — not `lang3`) |

## What was vendored

Two corpora are vendored:

- `tests/corpus/commons_lang/StringUtils.java`: only
  `org.apache.commons.lang.StringUtils.reverse(String str)` plus the class
  header, package declaration, public constructor, and Apache 2.0 license
  header. The trimmed file is ~70 lines.
- `tests/corpus/commons_lang_full/org/apache/commons/lang/**`: the Commons
  Lang 2.6 source files needed for JavaParser to resolve the upstream
  6594-line `StringUtils.java` and its referenced helper classes. Files
  were copied from the upstream `commons-lang-2.6-sources.jar` and converted
  from ISO-8859-1 source encoding to UTF-8 for current tooling.

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

## Why both corpora exist

The OMNIX semantic emitter is strict on symbol resolution per R-3.3 — every
referenced type must resolve via Reflection (java.lang.*), the source dir,
or supplied classpath JARs. The full 6594-line `StringUtils.java` references
~20 internal Commons Lang types (`StrBuilder`, `ArrayUtils`, `WordUtils`,
`Validate`, ...).

The M1 rebuild pipeline is verified end-to-end against the trimmed corpus.
M2 needs the full source shape for whole-module migration rehearsals, so the
full corpus is vendored separately rather than replacing the small M1 fixture.

## License notice

Copyright Apache Software Foundation. Licensed under the Apache License,
Version 2.0. Full license:
`http://www.apache.org/licenses/LICENSE-2.0`

The Apache license header is preserved verbatim at the top of vendored
source files. The trim is documented in the trimmed file's class-level
JavaDoc. No author attribution was removed from the full corpus.

OMNIX vendors these files as test data only. They are not part of any
distributable artifact.
