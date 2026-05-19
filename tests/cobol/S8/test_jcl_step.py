from __future__ import annotations

from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_step() -> None:
    j = parse_jcl_text("a.jcl", "//MYJOB JOB\n//S1 EXEC PGM=ABC\n")
    assert j.steps[0].name == "S1"
