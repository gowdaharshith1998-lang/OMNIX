# M1 Demo — Java 6 → Java 21 rebuild with signed receipt

The OMNIX M1 rebuild pipeline turns a Java 6 method into idiomatic Java 21
and emits a cryptographically signed receipt that anyone can verify
offline against the project's public key. This page describes what the
demo shows, how to reproduce it locally, what the receipt records, and —
critically — what it does **not** establish.

## What the demo shows

A single terminal run, end-to-end, ~60-90 seconds wall-clock:

1. `omnix analyze tests/corpus/commons_lang/` — ingests one Java 6 source
   file (Apache Commons Lang 2.6's `StringUtils.reverse(String)`, trimmed
   subset under Apache 2.0; see `tests/corpus/COMMONS_LANG_LICENSE.md`).
2. `omnix rebuild ... --target java21 --node-filter '*StringUtils.reverse'`
   — runs the full M1 pipeline:
     - load the graph node for `org.apache.commons.lang.StringUtils.reverse`
     - generate a spec (5 tractable passes)
     - format the deterministic prompt
     - dispatch one LLM call via `omnix.fabric` (vault-credentialed,
       routed to `anthropic` by the `claude-opus-4.7` model prefix)
     - run gates 1-3 mechanically (syntactic, typecheck, signature)
     - mark gate 4 (dependency) as `skipped` — M1 follow-up
     - mark gates 5+6 as `deferred_m2` — see honesty gate below
     - sign the result with the project Ed25519 key and write three files:
       - `.omnix/receipts/rebuilds/<ts>/<fqn>.java`  — rebuilt source
       - `.omnix/receipts/rebuilds/<ts>/<fqn>.json`  — canonical receipt
       - `.omnix/receipts/rebuilds/<ts>/<fqn>.sig`   — base64 Ed25519 sig
3. `omnix axiom verify-rebuild <receipt.json> --pubkey ...` — verifies
   the signature offline against the project's public key, reports
   `verified: true` + a `gates_summary` showing the breakdown by status.
4. `cat <rebuilt source>` — displays the LLM's Java 21 output verbatim.

## What the receipt records

Strongly, with the project's Ed25519 public key:

- The rebuilt source has not been tampered with since signing.
- The receipt's `legacy_source_sha256` anchors the exact bytes of the
  Java 6 input — a future auditor can re-hash the corpus file and
  confirm it's what the rebuild was performed against.
- Gates 1-3 (syntactic, type-check, signature) ran mechanically and
  passed. Their status is in the receipt's `gate_results` array.
- The receipt records the requested model ID, UTC timestamp, and
  prompt-template version.
- The receipt's canonical JSON is deterministic — two receipts built
  from the same logical inputs sign-equal.

## What the receipt does NOT establish (deferred to M2)

This distinction is load-bearing for OMNIX's positioning. The receipt
**explicitly** marks these gates `deferred_m2`, never `passed`:

- **Gate 5 — property-based testing.** M2 will wire Hypothesis-Java to
  derive properties from the spec and check the rebuild against them
  (e.g. `reverse(reverse(s)) == s` for all `s`).
- **Gate 6 — behavioral equivalence.** M2 will build the dual-runtime
  harness: run both the legacy Java 6 source and the rebuilt Java 21
  source on the same inputs, diff outputs.

The `RebuildReceipt` schema enforces this via
`GateResult.__post_init__`: a gate-5 or gate-6 marker with
`status='passed'` raises immediately. The honesty gate cannot be
silently bypassed.

Additionally, gate 4 (dependency) is marked `skipped` in M1 receipts —
the mechanical dep-check is a Phase-6 follow-up slice. `skipped` is
distinct from `deferred_m2`: skipped = "didn't run this time"; deferred
= "this category of verification doesn't exist in M1".

## Reproduce

### Prerequisites

```bash
# JDK 21+ (JavaParser bridge target)
javac -version    # need 21+

# Vendored JavaParser stack (one-time)
bash src/omnix/semantic/java/jvm/build.sh
# → OK: emitter functional

# Project Ed25519 keypair for signing
omnix axiom keygen --project .

# At least one Anthropic key in the Provider Fabric vault
# (BYOK UI in Studio, or programmatic via omnix.receipts.provider_vault)
```

### Drive the demo

The repo ships `docs/m1_demo_rehearsal.sh` which drives the full flow
end-to-end against a clean tmp workspace. Run it directly to see the
output without recording:

```bash
bash docs/m1_demo_rehearsal.sh
```

The script:
- Copies `tests/corpus/commons_lang/` to a scratch dir under `/tmp`.
- Runs `omnix analyze` to populate the graph.
- Runs `omnix rebuild ... --node-filter '*StringUtils.reverse'`.
- Runs `omnix axiom verify-rebuild` on the resulting receipt.
- Cats the rebuilt Java 21 source.

Expected wall-clock: ~60-90 seconds depending on LLM latency. Cost depends on
the selected model and current provider pricing. The script does NOT cache LLM
responses — every run is a fresh API call. Caching would defeat the
demo's epistemic value.

### Record (operator action)

The recording itself is **not** automated. Producing a credible demo
requires a single live take + a human watching to redo bad takes:

```bash
# Install asciinema (one-time)
sudo dnf install asciinema    # or: brew install asciinema

# Rehearse off-camera until you can hit the flow cleanly
bash docs/m1_demo_rehearsal.sh

# When ready, record:
asciinema rec docs/m1_demo.cast \
    --idle-time-limit 2 \
    --command "bash docs/m1_demo_rehearsal.sh"
```

Recording constraints:
- Do NOT record at >1x speed.
- Do NOT edit / splice / cut the cast.
- Do NOT include `cd ~/demo-scratch && rm -rf ...` setup commands in the
  recording — handle setup off-camera.
- Verify no API keys, no Vault contents, no `env | grep` output appear
  in the cast.
- Target ≤95 seconds total runtime.

For public provenance, record an unedited asciinema session. If a take fails,
re-record rather than editing.

## Provenance

- **Source**: Apache Commons Lang 2.6 (Apache 2.0), trimmed subset.
  See `tests/corpus/COMMONS_LANG_LICENSE.md` for the single documented
  edit (internal `StrBuilder` → `java.lang.StringBuilder` so the file
  parses in isolation).
- **Model**: `claude-opus-4.7` (the default; overridable via `--model`).
- **Prompt template version**: `v1-2026-05-17` (pinned in
  `omnix.orchestrator.prompt_template.PROMPT_TEMPLATE_VERSION`).
- **Signing key**: per-project Ed25519 keypair generated by
  `omnix axiom keygen`. Same keypair signs finding receipts.

## When to re-record

Any of these requires a fresh take:

- Bump of `PROMPT_TEMPLATE_VERSION` (changes the prompt → changes the
  rebuild → changes the receipt).
- Bump of the default model (`claude-opus-4.7` → `claude-opus-5.0` etc).
- New default value of `--target` (currently always `java21`).
- Schema bump on `RebuildReceipt` (`schema_version` major change).
- Any change to the gate set (M2 will land gates 5+6; the receipt then
  stops marking them `deferred_m2`).

Cosmetic OMNIX changes (CLI help text, logging tweaks) do not require
re-recording.
