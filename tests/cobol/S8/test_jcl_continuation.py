from __future__ import annotations

from omnix.parser.jcl.parser import parse_jcl_text


def test_jcl_continuation() -> None:
    line1 = "//S1 EXEC PGM=ABCD" + (" " * 52) + "X"
    line2 = "//         ,PARM=A"
    j = parse_jcl_text("a.jcl", f"//JOB JOB\n{line1}\n{line2}\n")
    assert j.steps
