"""Round-trip (encode/decode) invariant pair detection."""

from __future__ import annotations

from pathlib import Path

from omnix.verify import invariants

FIX = Path(__file__).parent / "fixtures" / "sample_roundtrip.py"


def test_encode_decode() -> None:
    funcs = invariants.function_names_in_file(FIX)
    pl = invariants.detect_invariant_pairs_in_file(
        FIX, allowed_names=funcs, file_scope_path=FIX
    )
    got = {(a, b) for a, b in pl}
    assert ("encode", "decode") in got or ("decode", "encode") in got


def test_push_pop() -> None:
    funcs = invariants.function_names_in_file(FIX)
    pl = invariants.detect_invariant_pairs_in_file(
        FIX, allowed_names=funcs, file_scope_path=FIX
    )
    got = {(a, b) for a, b in pl}
    assert ("push", "pop_str") in got


def test_empty() -> None:
    p = FIX.parent / "empty_invariants.py"
    p.write_text("def a():\n" "  pass\n", encoding="utf-8")
    try:
        fns = invariants.function_names_in_file(p)
        pl = invariants.detect_invariant_pairs_in_file(
            p, fns, file_scope_path=p
        )
        assert pl == []
    finally:
        p.unlink(missing_ok=True)


def test_skip_pair_when_first_not_in_target() -> None:
    """`local_only` is not a name in the target file — skip the (local_only, encode) chain."""
    p = Path(__file__).parent / "fixtures" / "inv_pair_caller.py"
    p.write_text(
        "def local_only():\n"
        "  return 1\n"
        "def c():\n"
        "  y = local_only()\n"
        "  z = encode(y)\n",
        encoding="utf-8",
    )
    try:
        scope = invariants.function_names_in_file(FIX)
        pl = invariants.detect_invariant_pairs_in_file(
            p, allowed_names=scope, file_scope_path=FIX
        )
        for a, b in pl:
            assert a in scope
            assert b in scope
    finally:
        p.unlink(missing_ok=True)
