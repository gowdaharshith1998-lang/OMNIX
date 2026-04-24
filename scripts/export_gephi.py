#!/usr/bin/env python3
"""
Dump OMNIX graph (AXIOM v2) to GEXF for Gephi layout exploration.
Schema: nodes(id, name, type), edges(id, source_id, target_id, relationship, metadata)
"""
import sqlite3
import sys
from pathlib import Path

DB  = Path.home() / "omnix" / "omnix.db"
OUT = Path.home() / "omnix" / "graph.gexf"

def x(s):
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))

def main():
    if not DB.exists():
        print(f"ERROR: {DB} not found", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(DB)
    cur = con.cursor()

    nodes = cur.execute("SELECT id, name, type FROM nodes").fetchall()
    edges = cur.execute("SELECT id, source_id, target_id, relationship FROM edges").fetchall()

    print(f"Exporting {len(nodes)} nodes, {len(edges)} edges...")

    with OUT.open("w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">\n')
        f.write('  <meta><creator>OMNIX</creator><description>AXIOM v2 code graph</description></meta>\n')
        f.write('  <graph mode="static" defaultedgetype="directed">\n')
        f.write('    <attributes class="node">\n')
        f.write('      <attribute id="0" title="type" type="string"/>\n')
        f.write('    </attributes>\n')
        f.write('    <attributes class="edge">\n')
        f.write('      <attribute id="1" title="relationship" type="string"/>\n')
        f.write('    </attributes>\n')
        f.write('    <nodes>\n')
        for nid, nname, ntype in nodes:
            f.write(
                f'      <node id="{x(nid)}" label="{x(nname)}">'
                f'<attvalues><attvalue for="0" value="{x(ntype)}"/></attvalues>'
                f'</node>\n'
            )
        f.write('    </nodes>\n')
        f.write('    <edges>\n')
        for eid, src, tgt, rel in edges:
            f.write(
                f'      <edge id="{eid}" source="{x(src)}" target="{x(tgt)}">'
                f'<attvalues><attvalue for="1" value="{x(rel)}"/></attvalues>'
                f'</edge>\n'
            )
        f.write('    </edges>\n')
        f.write('  </graph>\n')
        f.write('</gexf>\n')

    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"✓ Wrote {len(nodes)} nodes, {len(edges)} edges → {OUT} ({size_mb:.2f} MB)")
    print(f"")
    print(f"Open in Gephi:")
    print(f"  flatpak run org.gephi.Gephi {OUT}")

if __name__ == "__main__":
    main()
