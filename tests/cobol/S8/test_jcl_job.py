from __future__ import annotations

from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_job() -> None:
    j = parse_jcl_text("a.jcl", "//MYJOB JOB\n")
    assert j.name == "MYJOB"
