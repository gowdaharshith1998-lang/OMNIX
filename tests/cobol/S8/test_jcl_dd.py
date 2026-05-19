from __future__ import annotations

from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_dd() -> None:
    j = parse_jcl_text("a.jcl", "//MYJOB JOB\n//S1 EXEC PGM=ABC\n//IN DD DISP=SHR\n")
    assert j.steps[0].dds[0].name == "IN"
