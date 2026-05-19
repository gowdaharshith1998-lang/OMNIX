from __future__ import annotations

from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_proc() -> None:
    j = parse_jcl_text("a.jcl", "//P1 PROC\n")
    assert j.procs[0].name == "P1"
