"""Smoke tests for OMNIX parsers."""

from __future__ import annotations

import os
import tempfile
import unittest

from src.graph.store import GraphStore
from src.parser.python_parser import parse_python_files
from src.parser.typescript_parser import parse_typescript_files

SAMPLE_PY = '''
import os
from pathlib import Path

@deco
class C(Base):
    def meth(self):
        helper()

def outer():
    def inner():
        pass
    inner()
'''

SAMPLE_TS = '''
import { useState } from "react";

export function Page() {
  const [x, setX] = useState(0);
  return x;
}

class Box extends Thing {
  go() {
    Page();
  }
}
'''


class ParserTests(unittest.TestCase):
    def test_python_parser_extracts_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "sample.py")
            with open(p, "w", encoding="utf-8") as f:
                f.write(SAMPLE_PY)
            store = GraphStore(os.path.join(tmp, "t.db"))
            store.reset()
            n = parse_python_files(tmp, store)
            self.assertEqual(n, 1)
            ids = {x.id for x in store.get_all_nodes()}
            self.assertIn("sample.py", ids)
            self.assertIn("sample.py::C", ids)
            self.assertIn("sample.py::C.meth", ids)
            self.assertIn("sample.py::outer", ids)
            self.assertIn("sample.py::outer.inner", ids)
            rels = {(e.source_id, e.relationship, e.target_id) for e in store.get_all_edges()}
            self.assertIn(("sample.py", "DEFINES", "sample.py::C"), rels)

    def test_typescript_parser_extracts_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "mod.ts")
            with open(p, "w", encoding="utf-8") as f:
                f.write(SAMPLE_TS)
            store = GraphStore(os.path.join(tmp, "t.db"))
            store.reset()
            n = parse_typescript_files(tmp, store)
            self.assertEqual(n, 1)
            ids = {x.id for x in store.get_all_nodes()}
            self.assertIn("mod.ts", ids)
            self.assertIn("mod.ts::Page", ids)
            self.assertIn("mod.ts::Box", ids)
            self.assertIn("mod.ts::Box.go", ids)

    def test_graph_store_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = GraphStore(os.path.join(tmp, "t.db"))
            store.reset()
            store.add_node("a::f", "foo", "function", "a.py", 1, 5, 3, None)
            store.commit()
            hits = store.search("foo")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].id, "a::f")


if __name__ == "__main__":
    unittest.main()
