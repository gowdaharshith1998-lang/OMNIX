# OMNIX 60-Second Demo Script

This script is for a short screen recording linked near the top of the README.
The goal is to show that OMNIX runs, emits signed evidence, and detects
tampering.

## Setup

Run from the repo root.

```powershell
$project = Resolve-Path "demos/petclinic"
python -m pip install -r requirements.txt
python omnix.py axiom keygen --project $project
```

If `omnix` is installed in the active environment, `omnix ...` can replace
`python omnix.py ...`.

## Recording Beats

### 1. Analyze the codebase

Voiceover:

> OMNIX starts by parsing a real codebase into a program graph. This demo uses
> the Spring Petclinic sample app staged in the repo.

Command:

```powershell
python omnix.py analyze $project --no-open
```

Cut after the command shows the local Studio/API start message.

### 2. Emit signed bug-scan receipts

Voiceover:

> Next I run the property-based bug scanner with receipt emission. Findings are
> not just printed; they are signed into an audit trail.

Command:

```powershell
python omnix.py find-bugs $project --examples 5 --top 3 --emit-receipts
```

### 3. Verify the latest scan

Voiceover:

> The scan directory includes per-finding Ed25519 receipts and an ML-DSA-65
> manifest over the Merkle root. A third party can verify it offline.

Commands:

```powershell
$scan = Get-ChildItem "$HOME\.omnix\receipts\findings" -Recurse -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName "scan_manifest.json") } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

python omnix.py axiom verify-scan "$($scan.FullName)"
```

Expected result:

```text
verified  finding_count=<n>
```

### 4. Tamper one byte and show failure

Voiceover:

> Now I change one receipt. The same verifier fails, which is the whole point:
> the evidence is tamper-evident.

Commands:

```powershell
$receipt = Get-ChildItem "$($scan.FullName)" -Filter "*.json" |
  Where-Object { $_.Name -ne "scan_manifest.json" } |
  Select-Object -First 1

Copy-Item "$($receipt.FullName)" "$($receipt.FullName).bak"
(Get-Content "$($receipt.FullName)" -Raw).Replace('"schema_version"', '"schema_version_tampered"') |
  Set-Content "$($receipt.FullName)" -NoNewline

python omnix.py axiom verify-scan "$($scan.FullName)"
Move-Item "$($receipt.FullName).bak" "$($receipt.FullName)" -Force
```

Expected result:

```text
FAIL: finding_signature_invalid
```

## 60-Second Voiceover

> I built OMNIX, a graph-native migration engine for legacy systems. It parses a
> real codebase into a typed program graph, runs verification and property-based
> checks, and emits signed receipts for every finding or transformation. Here it
> analyzes Spring Petclinic, runs a signed bug scan, verifies the scan offline,
> then fails verification after I tamper with one byte. The point is not just
> code generation; it is auditable evidence that reviewers and auditors can
> inspect.

## Outreach Sentence

I built OMNIX: a graph-native legacy-modernization engine with Tree-sitter code
analysis, six-gate verification, property-based testing, and post-quantum signed
receipts for every finding or transformation.

## LinkedIn Bio

Building OMNIX, a source-available legacy-modernization engine that turns
codebases into typed program graphs, runs verification gates over changes, and
emits tamper-evident signed receipts for audit review. Focus areas:
Python/TypeScript systems, code intelligence, property-based testing, migration
tooling, and AI-assisted engineering workflows I can explain end to end.
