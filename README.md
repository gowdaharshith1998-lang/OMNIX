# OMNIX

**The Code Intelligence Engine.**

Point OMNIX at any codebase. Get an interactive 3D hologram of every file, function, class, and connection.

## Quick Start

```bash
pip install -r requirements.txt
python omnix.py analyze /path/to/your/project
```

Browser opens. Explore your codebase in 3D.

Use `python omnix.py analyze /path --no-open` to only build `omnix.db` and `src/web/graph_data.json` without starting the server.

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
- Self-healing: OMNIX finds bugs AND generates fixes
- MCP server for Cursor / Claude Code integration

## License

MIT
