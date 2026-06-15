# OMNIX Documentation

This is the index for OMNIX's operator, architecture, data-migration,
deployment, security, and positioning documentation. Each entry below links to a
single document with a one-line description. Root-level project files are linked
with `../`.

For the product overview, CLI quickstart, and license terms, start with the root
[`README.md`](../README.md).

## Getting started

- [`../README.md`](../README.md) — product overview, CLI quickstart, and evaluation roadmap.
- [`M1_DEMO.md`](M1_DEMO.md) — Java 6 → Java 21 rebuild with a signed receipt you can verify offline.
- [`onboarding/scanning.md`](onboarding/scanning.md) — onboarding walkthrough for scanning a codebase with OMNIX.
- [`demo/60-second-demo.md`](demo/60-second-demo.md) — screen-recording script showing OMNIX run, signed evidence, and tamper detection.

## Architecture & concepts

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — system architecture: parsers, program graph, rebuild, verification, and receipts.
- [`PHASES.md`](PHASES.md) — shipped surfaces, active implementation tracks, and planned milestones.
- [`LEGACY_LANGUAGE_SUPPORT.md`](LEGACY_LANGUAGE_SUPPORT.md) — quality scoring and grammar support for COBOL, IBM HLASM, and Fortran.
- [`QUALITY_PROFILE_BASELINES.md`](QUALITY_PROFILE_BASELINES.md) — observed per-grammar mean-quality baselines measured on real public codebases.

## Data migration (OMNIX-DM)

- [`dm/README.md`](dm/README.md) — overview of the D1–D5 data-migration pipeline and its signed receipt chain.
- [`dm/d1-schema-understanding.md`](dm/d1-schema-understanding.md) — D1: parse schemas, extract metadata, and propose reviewed column mappings.
- [`dm/d2-edge-case-profiling.md`](dm/d2-edge-case-profiling.md) — D2: plan and run edge-case probes, surfacing blockers explicitly.
- [`dm/d3-transformation-synthesis.md`](dm/d3-transformation-synthesis.md) — D3: synthesize per-column transformer specs with property-derived checks.
- [`dm/d4-bulk-import.md`](dm/d4-bulk-import.md) — D4: apply transformers across all rows, write target batches, and quarantine failures.
- [`dm/d5-change-data-capture.md`](dm/d5-change-data-capture.md) — D5: replay PostgreSQL logical changes, track lag, and propose cutover.
- [`dm/runbook.md`](dm/runbook.md) — operator runbook for the D1–D2 Python invocation patterns.
- [`dm/academic-foundation.md`](dm/academic-foundation.md) — the Wang / Dillig (UT Austin) research the DM pipeline builds on.

## Deployment

- [`deploy/airgap.md`](deploy/airgap.md) — installing OMNIX into a customer-controlled Kubernetes cluster with no internet egress.

## Security

- [`../SECURITY.md`](../SECURITY.md) — supported versions and how to report a vulnerability.
- [`THREAT_MODEL.md`](THREAT_MODEL.md) — threat-model notes for subprocess execution in the verification gates.

## Project & positioning

- [`marketing/landing.md`](marketing/landing.md) — source-of-truth marketing landing copy.
- [`marketing/marketplace_listing.md`](marketing/marketplace_listing.md) — GitHub Marketplace listing copy for OMNIX Replication.

## Reference

- [`../CHANGELOG.md`](../CHANGELOG.md) — notable changes per release.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — how to set up, build, and contribute.
- [`../GOVERNANCE.md`](../GOVERNANCE.md) — project governance and decision-making.
- [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) — expected conduct for participants.
- [`../LICENSE`](../LICENSE) — OMNIX custom evaluation license terms.
