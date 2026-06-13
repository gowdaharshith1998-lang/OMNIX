"""pgoutput binary parser tests (P8). All synthetic byte streams — no live PG."""

from __future__ import annotations

import datetime
import struct

import pytest

from omnix.dm._types import ChangeEvent, RelationSchema
from omnix.dm.d5_change_data_capture.pg_adapter.pgoutput_parser import (
    ParseError,
    _lsn_str,
    _State,
    _UnchangedToast,
    parse_message,
)


def _cstr(s: str) -> bytes:
    return s.encode("utf-8") + b"\x00"


def _relation_msg(
    relation_id: int,
    schema: str,
    table: str,
    columns,
    *,
    replica: str = "d",
) -> bytes:
    body = (
        b"R"
        + struct.pack(">I", relation_id)
        + _cstr(schema)
        + _cstr(table)
        + replica.encode("ascii")
        + struct.pack(">H", len(columns))
    )
    for (name, type_oid, is_key) in columns:
        body += (
            struct.pack(">B", 0x01 if is_key else 0x00)
            + _cstr(name)
            + struct.pack(">I", type_oid)
            + struct.pack(">i", -1)
        )
    return body


def _begin_msg(final_lsn: int = 0x0000016B5D68, commit_ts: int = 0, xid: int = 42) -> bytes:
    return b"B" + struct.pack(">QqI", final_lsn, commit_ts, xid)


def _commit_msg(end_lsn: int = 0x0000016B5D70, commit_ts: int = 0) -> bytes:
    return b"C" + struct.pack(">BQQq", 0, 0, end_lsn, commit_ts)


def _text_col(text: str) -> bytes:
    enc = text.encode("utf-8")
    return b"t" + struct.pack(">I", len(enc)) + enc


def _null_col() -> bytes:
    return b"n"


def _unchanged_col() -> bytes:
    return b"u"


def _insert_msg(relation_id: int, columns_bytes: bytes, n_cols: int) -> bytes:
    return (
        b"I"
        + struct.pack(">I", relation_id)
        + b"N"
        + struct.pack(">H", n_cols)
        + columns_bytes
    )


def _update_msg(relation_id: int, new_bytes: bytes, n_cols: int, *, old_bytes=None, old_marker=b"K") -> bytes:
    body = b"U" + struct.pack(">I", relation_id)
    if old_bytes is not None:
        body += old_marker + struct.pack(">H", n_cols) + old_bytes
    body += b"N" + struct.pack(">H", n_cols) + new_bytes
    return body


def _delete_msg(relation_id: int, old_bytes: bytes, n_cols: int, *, old_marker=b"K") -> bytes:
    return (
        b"D"
        + struct.pack(">I", relation_id)
        + old_marker
        + struct.pack(">H", n_cols)
        + old_bytes
    )


def _truncate_msg(relation_ids) -> bytes:
    return (
        b"T"
        + struct.pack(">I", len(relation_ids))
        + struct.pack(">B", 0)
        + b"".join(struct.pack(">I", r) for r in relation_ids)
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_relation_msg_cached():
    state = _State(relations={})
    out = parse_message(
        _relation_msg(1234, "public", "owners", [("id", 23, True), ("email", 25, False)]),
        state,
    )
    assert out is None
    assert 1234 in state.relations
    assert state.relations[1234].columns[0] == ("id", 23, True)


def test_begin_then_commit_updates_state():
    state = _State(relations={})
    parse_message(_begin_msg(final_lsn=100, xid=7), state)
    assert state.current_xid == 7
    assert state.current_lsn is not None
    parse_message(_commit_msg(end_lsn=200), state)
    assert state.current_xid is None


def test_insert_with_text_and_null_columns():
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "owners", [("id", 23, True), ("email", 25, False)]), state)
    parse_message(_begin_msg(), state)
    cols = struct.pack(">I", 1) + b"42" + _null_col()  # wait — _text_col already includes len + 't'
    cols = _text_col("42") + _null_col()
    event = parse_message(_insert_msg(1, cols, 2), state)
    assert isinstance(event, ChangeEvent)
    assert event.op == "I"
    assert event.after == (("id", 42), ("email", None))


def test_insert_with_unchanged_toast_sentinel():
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "t", [("id", 23, True), ("blob", 25, False)]), state)
    parse_message(_begin_msg(), state)
    cols = _text_col("1") + _unchanged_col()
    event = parse_message(_insert_msg(1, cols, 2), state)
    assert isinstance(event.after[1][1], _UnchangedToast)


def test_update_with_key_only_old():
    state = _State(relations={})
    parse_message(
        _relation_msg(1, "public", "t", [("id", 23, True), ("name", 25, False)], replica="d"),
        state,
    )
    parse_message(_begin_msg(), state)
    old = _text_col("5") + _null_col()
    new = _text_col("5") + _text_col("renamed")
    ev = parse_message(_update_msg(1, new, 2, old_bytes=old, old_marker=b"K"), state)
    assert ev.op == "U"
    assert ev.before == (("id", 5), ("name", None))
    assert ev.after == (("id", 5), ("name", "renamed"))


def test_update_with_full_old_tuple():
    state = _State(relations={})
    parse_message(
        _relation_msg(1, "public", "t", [("id", 23, True), ("name", 25, False)], replica="f"),
        state,
    )
    parse_message(_begin_msg(), state)
    old = _text_col("9") + _text_col("old_name")
    new = _text_col("9") + _text_col("new_name")
    ev = parse_message(_update_msg(1, new, 2, old_bytes=old, old_marker=b"O"), state)
    assert ev.before == (("id", 9), ("name", "old_name"))


def test_delete_with_key_only():
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "t", [("id", 23, True)]), state)
    parse_message(_begin_msg(), state)
    old = _text_col("7")
    ev = parse_message(_delete_msg(1, old, 1), state)
    assert ev.op == "D"
    assert ev.before == (("id", 7),)
    assert ev.after is None


def test_truncate_surfaced_in_unhandled():
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "t", [("id", 23, True)]), state)
    parse_message(_begin_msg(), state)
    ev = parse_message(_truncate_msg([1]), state)
    assert ev is not None and ev.op == "T"
    assert "Truncate" in state.unhandled_event_types


def test_unknown_relation_in_insert_raises_parse_error():
    state = _State(relations={})
    parse_message(_begin_msg(), state)
    with pytest.raises(ParseError):
        parse_message(_insert_msg(99, _text_col("1"), 1), state)


def test_corrupted_length_prefix_raises_parse_error():
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "t", [("v", 25, False)]), state)
    parse_message(_begin_msg(), state)
    # Length prefix promises 1000 bytes but we only supply 4
    bad = b"I" + struct.pack(">I", 1) + b"N" + struct.pack(">H", 1) + b"t" + struct.pack(">I", 1000) + b"abc"
    with pytest.raises(ParseError):
        parse_message(bad, state)


def test_unknown_message_byte_recorded_not_dropped():
    state = _State(relations={})
    # 'Z' is not a known pgoutput tag.
    parse_message(b"Z", state)
    assert "Z" in state.unhandled_event_types


def test_numeric_oid_1700_decoded_as_decimal():
    import decimal

    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "t", [("amt", 1700, True)]), state)
    parse_message(_begin_msg(), state)
    ev = parse_message(_insert_msg(1, _text_col("3.14"), 1), state)
    assert isinstance(ev.after[0][1], decimal.Decimal)
    assert ev.after[0][1] == decimal.Decimal("3.14")


def test_timestamptz_oid_1184_decoded_with_tzinfo():
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "t", [("ts", 1184, True)]), state)
    parse_message(_begin_msg(), state)
    ev = parse_message(_insert_msg(1, _text_col("2026-05-27 14:00:00+00"), 1), state)
    val = ev.after[0][1]
    assert isinstance(val, datetime.datetime)
    assert val.tzinfo is not None


def test_large_tuple_parses():
    cols_spec = [(f"c{i}", 25, i == 0) for i in range(200)]
    state = _State(relations={})
    parse_message(_relation_msg(1, "public", "wide", cols_spec), state)
    parse_message(_begin_msg(), state)
    tuple_bytes = b"".join(_text_col(str(i)) for i in range(200))
    ev = parse_message(_insert_msg(1, tuple_bytes, 200), state)
    assert len(ev.after) == 200


def test_lsn_str_format():
    # PG ``X/YYYYYYYY`` is (high 32 / low 32) of the 64-bit LSN.
    assert _lsn_str(0x0000016B5D68) == "0/16B5D68"
    assert _lsn_str(0x100000000) == "1/0"
    assert _lsn_str(0) == "0/0"


def test_empty_payload_raises():
    state = _State(relations={})
    with pytest.raises(ParseError):
        parse_message(b"", state)
