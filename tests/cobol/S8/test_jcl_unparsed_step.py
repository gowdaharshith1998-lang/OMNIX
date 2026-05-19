from __future__ import annotations

from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_unparsed_step() -> None:
    j = parse_jcl_text("a.jcl", "//JOB JOB\n//S1 EXEC PGM=A\n//BAD XYZ\n")
    assert j.steps[0].unparsed
