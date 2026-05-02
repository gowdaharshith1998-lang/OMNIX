# OMNIX

**OMNIX is, to our current knowledge, the only open-core code intelligence product that bundles universal Tree-Sitter parsing + self-evolving query patterns with ML-DSA-65 signed audit trail + hybrid universal PBT + sandbox-isolated auto-fix in one shipping repo.**

Point OMNIX at a codebase. Get an interactive 3D graph of every file, function, class, and connection.

## Quick Start

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

Browser opens. Explore your codebase in 3D.

Use `python omnix.py analyze /path --no-open` to start the React Studio server without launching a browser. Studio ingests into `<path>/.omnix/omnix.db`; the legacy `src/web/graph_data.json` export path is retired.

## Grammar Visibility (v0.4)

OMNIX exposes what the universal parser has learned: per-language profiles, pattern counts, recent grammar mutations, unknown file extensions, optional LLM call budget, and ML-DSA-signed evolution receipts (compliance-**aligned** design — not a certification).

### CLI

```bash
omnix grammar status
omnix grammar status --json
# Optional: --db /path/to/omnix.db  --grammar python
```

Sample table (from this repo after analyze):

```
Grammar     Files parsed  Avg quality  …  Active patterns  Recent mutations  Last evolution receipt
python      2844          0.755        …  10               7                 …/evolution_…_python.json
rust        14            0.750        …  1                0                 —
typescript  1597          0.610        …  18               4                 …/evolution_…_typescript.json
```

JSON mirrors API field names: `grammar_name`, `files_parsed`, `avg_quality`, `parse_modes`, `active_patterns`, `recent_mutations_30d`, `last_evolution_receipt`, plus `unknown_extensions`, `llm_fallback`.

### API (read-only, localhost-only)

| Route | Returns (abbrev.) |
|-------|-------------------|
| `GET /api/grammar/status` | `db_path`, `generated_at`, `grammars[]`, `unknown_extensions[]`, `llm_fallback` |
| `GET /api/grammar/mutations?limit=N` | `mutations[]` with `grammar_name`, `node_type`, `action`, `observed_at`, `receipt_path`, `sig_path`, `receipt_exists`, `sig_exists` |
| `GET /api/grammar/unknown-extensions` | `total`, `extensions[]` (`ext`, `first_seen_at`, optional `raw_bytes_hex`) |
| `GET /api/fabric/llm-budget` | `budget_*`, `calls_today`, `available` (often null when unset) |
| `POST /api/grammar/verify-receipt` | `verified`, `verifier_output`, `receipt_path`, `sig_path`, `verified_at` |

Non-localhost requests get **403**. Verify rejects paths outside canonical receipt dirs (**400** / **404**).

### Studio

Open **Grammar Health** in the left rail (chart icon between Receipts and Settings). Four GETs poll every 10s; **Verify** POSTs `{ "receipt_path": "<abs path>" }`.

![Grammar Health drawer](docs/images/grammar-health-drawer.png)

### Roadmap

**Slice 18d (in progress)** — extend the same receipt story to `find_bugs` / LLM outputs (Compliance Vault tier). Not shipped in v0.4.

## What It Does

- 🔍 Parses Python + TypeScript with Tree-sitter
- 🧬 Builds a knowledge graph of every symbol and relationship
- 🌐 Renders an interactive 3D force graph in your browser
- ⚡ Click any node to see what it connects to
- 🔎 Search for any function, class, or file
- 📊 Stats: files, functions, classes, imports, edges

## Coming Soon

- AI agents that understand your product and test it like a human
- Full-stack failure tracing (UI → API → DB → root cause)
- Self-healing: OMNIX finds bugs and proposes sandbox-only fixes
- MCP server for Cursor / Claude Code integration

## Adjacent prior art (each does part of the stack)

- **tree-sitter-language-pack** — large grammar bundle (300+); no built-in signed audit trail
- **Codebase-Memory (e.g. arXiv:2603.27277, multi-language, MCP tools)** — memory/retrieval layer; not the same as ML-DSA graph-event signing in-tree
- **pqrascv-core** — ML-DSA-65 attestation patterns for embedded Rust; different product surface
- **Sigstore / cosign** — software artifact signing and provenance; OMNIX signs code-intelligence *events* with ML-DSA-65, not OCI images
- **JQF, PropTest-AI** — property-based testing and LLM assistance; OMNIX’s Layer 5–7 ties PBT to graph + optional Fabric
- **Tian AI and similar (AST + LLM)** — self-modification experiments; OMNIX keeps evolution metadata signed and does not `eval` LLM output in-process for universal PBT

## License

MIT
