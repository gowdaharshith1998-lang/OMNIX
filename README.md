# OMNIX

**OMNIX is, to our current knowledge, the only open-core code intelligence product that bundles universal Tree-Sitter parsing + self-evolving query patterns with ML-DSA-65 signed audit trail + hybrid universal PBT + sandbox-isolated auto-fix in one shipping repo.**

Point OMNIX at a codebase. Get an interactive 3D graph of every file, function, class, and connection.

## Quick Start

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

Browser opens. Explore your codebase in 3D.

Use `python omnix.py analyze /path --no-open` to only build `<path>/omnix.db` and `src/web/graph_data.json` without starting the server.

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
