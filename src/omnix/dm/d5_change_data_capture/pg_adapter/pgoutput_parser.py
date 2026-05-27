"""Pure-Python parser for PostgreSQL ``pgoutput`` binary logical-decoding
messages (PG 18.4 format).

References:
  * PostgreSQL Source ``src/backend/replication/logical/proto.c``
  * PostgreSQL Docs § "Logical Decoding Output Plugin Interface" / pgoutput
  * Pierre Carbonnelle, "pypgoutput" PyPI 2022 (prototype reference; not a
    runtime dependency — pure-Python parser borrows protocol knowledge
    only)
  * Giulio Capelli, "CDC based on PostgreSQL logical replication" (Medium
    2025) — order-of-messages reference

Message types we parse:

  ``R`` — Relation: relation_id, schema, table, replica_identity, columns
  ``B`` — Begin: final_lsn, commit_timestamp, xid
  ``I`` — Insert: relation_id, 'N' tuple
  ``U`` — Update: relation_id, ['K' key-only old | 'O' full old], 'N' new
  ``D`` — Delete: relation_id, ['K' key-only old | 'O' full old]
  ``C`` — Commit: flags, commit_lsn, end_lsn, commit_timestamp
  ``T`` — Truncate: relation_count, flags, relation_id_array
            (PR C: surfaced in unhandled_event_types — PR D will replay)
  ``M`` — Message (logical decoding generic): name + payload; counted only
  ``Y`` — Type: known type metadata; we don't decode user types in PR C
  ``O`` — Origin; not used in PR C
"""

from __future__ import annotations

import datetime
import decimal
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from omnix.dm._types import ChangeEvent, RelationSchema


class ParseError(RuntimeError):
    """Raised when ``pgoutput`` bytes can't be interpreted. Never silently
    skipped — the orchestrator quarantines on this."""


# PG epoch is 2000-01-01 UTC (POSTGRES_EPOCH_JDATE diff in microseconds).
_PG_EPOCH = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


# Curated PG type OIDs we map to native Python types. Anything else stays as
# the raw text representation (which is what pgoutput sends with kind='t').
_OID_DECODERS: Dict[int, Any] = {
    16: lambda s: s == "t",  # bool
    20: int,                 # int8 / bigint
    21: int,                 # int2 / smallint
    23: int,                 # int4 / integer
    700: float,              # float4
    701: float,              # float8
    1700: lambda s: decimal.Decimal(s),  # numeric
    25: str,                 # text
    1043: str,               # varchar
    1042: str,               # bpchar
    1114: lambda s: datetime.datetime.fromisoformat(s.replace(" ", "T")),  # timestamp
    1184: lambda s: datetime.datetime.fromisoformat(
        s.replace(" ", "T")
    ).astimezone(datetime.timezone.utc),  # timestamptz
    1082: lambda s: datetime.date.fromisoformat(s),  # date
    17: lambda s: bytes.fromhex(s[2:]) if s.startswith("\\x") else s.encode(),  # bytea
}


def _decode_value(oid: int, raw: str) -> Any:
    decoder = _OID_DECODERS.get(oid)
    if decoder is None:
        return raw
    try:
        return decoder(raw)
    except Exception:
        return raw


def _lsn_str(value: int) -> str:
    """Render an 8-byte LSN integer as the canonical PG ``X/YYYYYYYY`` form."""
    return f"{(value >> 32):X}/{(value & 0xFFFFFFFF):X}"


def _pg_ts_to_iso(microseconds_since_pg_epoch: int) -> str:
    dt = _PG_EPOCH + datetime.timedelta(microseconds=microseconds_since_pg_epoch)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


class _Cursor:
    """Tiny byte-stream cursor with bounds-checked reads."""

    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def _need(self, n: int) -> None:
        if self.pos + n > len(self.buf):
            raise ParseError(
                f"truncated pgoutput message: need {n} more bytes at pos {self.pos} "
                f"(buffer len {len(self.buf)})"
            )

    def u8(self) -> int:
        self._need(1)
        v = self.buf[self.pos]
        self.pos += 1
        return v

    def i16(self) -> int:
        self._need(2)
        (v,) = struct.unpack_from(">h", self.buf, self.pos)
        self.pos += 2
        return v

    def u16(self) -> int:
        self._need(2)
        (v,) = struct.unpack_from(">H", self.buf, self.pos)
        self.pos += 2
        return v

    def i32(self) -> int:
        self._need(4)
        (v,) = struct.unpack_from(">i", self.buf, self.pos)
        self.pos += 4
        return v

    def u32(self) -> int:
        self._need(4)
        (v,) = struct.unpack_from(">I", self.buf, self.pos)
        self.pos += 4
        return v

    def i64(self) -> int:
        self._need(8)
        (v,) = struct.unpack_from(">q", self.buf, self.pos)
        self.pos += 8
        return v

    def u64(self) -> int:
        self._need(8)
        (v,) = struct.unpack_from(">Q", self.buf, self.pos)
        self.pos += 8
        return v

    def cstr(self) -> str:
        end = self.buf.find(b"\x00", self.pos)
        if end < 0:
            raise ParseError("unterminated C-string in pgoutput message")
        out = self.buf[self.pos : end].decode("utf-8", "replace")
        self.pos = end + 1
        return out

    def take(self, n: int) -> bytes:
        self._need(n)
        out = self.buf[self.pos : self.pos + n]
        self.pos += n
        return out


# ---------------------------------------------------------------------------
# Sub-message parsers
# ---------------------------------------------------------------------------


_REPLICA_IDENTITY = {
    ord("d"): "default",
    ord("n"): "nothing",
    ord("f"): "full",
    ord("i"): "index",
}


def _parse_relation(cur: _Cursor) -> RelationSchema:
    relation_id = cur.u32()
    schema_name = cur.cstr()
    table_name = cur.cstr()
    replica_identity_byte = cur.u8()
    column_count = cur.u16()
    columns: List[Tuple[str, int, bool]] = []
    for _ in range(column_count):
        flags = cur.u8()
        col_name = cur.cstr()
        type_oid = cur.u32()
        _atttypmod = cur.i32()
        columns.append((col_name, type_oid, bool(flags & 0x01)))
    return RelationSchema(
        relation_id=relation_id,
        schema_name=schema_name,
        table_name=table_name,
        columns=tuple(columns),
        replica_identity=_REPLICA_IDENTITY.get(replica_identity_byte, "default"),
    )


def _parse_tuple(cur: _Cursor, relation: RelationSchema) -> Tuple[Tuple[str, Any], ...]:
    n_cols = cur.u16()
    out: List[Tuple[str, Any]] = []
    for i in range(n_cols):
        kind = cur.u8()
        col_name = relation.columns[i][0] if i < len(relation.columns) else f"col_{i}"
        oid = relation.columns[i][1] if i < len(relation.columns) else 25
        if kind == ord("n"):
            out.append((col_name, None))
        elif kind == ord("u"):
            # TOAST unchanged — we surface a sentinel string so the replayer
            # can decide to skip-vs-fetch. PR D may grow this.
            out.append((col_name, _UnchangedToast()))
        elif kind in (ord("t"), ord("b")):
            length = cur.u32()
            data = cur.take(length)
            text = data.decode("utf-8", "replace") if kind == ord("t") else data.hex()
            out.append((col_name, _decode_value(oid, text)))
        else:
            raise ParseError(
                f"unknown tuple column kind {kind!r} at offset {cur.pos}"
            )
    return tuple(out)


class _UnchangedToast:
    """Sentinel for a column that was not present in the WAL (TOASTed and
    unchanged). The replayer either skips the column on UPDATE or fetches
    fresh data from legacy if needed; PR C surfaces the sentinel and lets
    the replayer decide. PR D may add a fetch path."""

    def __repr__(self) -> str:
        return "<UnchangedToast>"


def _parse_begin(cur: _Cursor) -> Tuple[int, int, int]:
    final_lsn = cur.u64()
    commit_ts = cur.i64()
    xid = cur.u32()
    return final_lsn, commit_ts, xid


def _parse_commit(cur: _Cursor) -> Tuple[int, int, int, int]:
    flags = cur.u8()
    commit_lsn = cur.u64()
    end_lsn = cur.u64()
    commit_ts = cur.i64()
    return flags, commit_lsn, end_lsn, commit_ts


# ---------------------------------------------------------------------------
# Public parse_message
# ---------------------------------------------------------------------------


@dataclass
class _State:
    """Parser state shared across messages within a transaction."""

    relations: Dict[int, RelationSchema]
    current_xid: Optional[int] = None
    current_commit_ts_iso: Optional[str] = None
    current_lsn: Optional[str] = None
    unhandled_event_types: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.unhandled_event_types is None:
            self.unhandled_event_types = []


def parse_message(
    payload: bytes,
    state: _State,
) -> Optional[ChangeEvent]:
    """Parse a single ``pgoutput`` message payload (the byte string the
    replication connection delivers via ``read_message``). Returns a
    ``ChangeEvent`` for ``I``/``U``/``D``/``T`` messages, ``None`` for
    others (whose effects are captured in ``state``).
    """
    if not payload:
        raise ParseError("empty pgoutput payload")
    cur = _Cursor(payload)
    tag = cur.u8()
    if tag == ord("R"):
        relation = _parse_relation(cur)
        state.relations[relation.relation_id] = relation
        return None
    if tag == ord("B"):
        final_lsn, commit_ts, xid = _parse_begin(cur)
        state.current_xid = xid
        state.current_commit_ts_iso = _pg_ts_to_iso(commit_ts)
        state.current_lsn = _lsn_str(final_lsn)
        return None
    if tag == ord("C"):
        _, _commit_lsn, end_lsn, commit_ts = _parse_commit(cur)
        state.current_lsn = _lsn_str(end_lsn)
        state.current_xid = None
        return None
    if tag == ord("I"):
        relation_id = cur.u32()
        rel = state.relations.get(relation_id)
        if rel is None:
            raise ParseError(f"Insert for unknown relation_id {relation_id}")
        tuple_kind = cur.u8()
        if tuple_kind != ord("N"):
            raise ParseError(f"Insert with non-'N' tuple kind {tuple_kind!r}")
        after = _parse_tuple(cur, rel)
        return ChangeEvent(
            op="I",
            relation_id=relation_id,
            schema_name=rel.schema_name,
            table_name=rel.table_name,
            lsn=state.current_lsn or "0/0",
            xid=state.current_xid or 0,
            commit_timestamp=state.current_commit_ts_iso,
            before=None,
            after=after,
        )
    if tag == ord("U"):
        relation_id = cur.u32()
        rel = state.relations.get(relation_id)
        if rel is None:
            raise ParseError(f"Update for unknown relation_id {relation_id}")
        before: Optional[Tuple[Tuple[str, Any], ...]] = None
        # Optional 'K' (key-only old) or 'O' (full old) before the 'N' new.
        marker = cur.u8()
        if marker in (ord("K"), ord("O")):
            before = _parse_tuple(cur, rel)
            marker = cur.u8()
        if marker != ord("N"):
            raise ParseError(f"Update missing 'N' new tuple (got {marker!r})")
        after = _parse_tuple(cur, rel)
        return ChangeEvent(
            op="U",
            relation_id=relation_id,
            schema_name=rel.schema_name,
            table_name=rel.table_name,
            lsn=state.current_lsn or "0/0",
            xid=state.current_xid or 0,
            commit_timestamp=state.current_commit_ts_iso,
            before=before,
            after=after,
        )
    if tag == ord("D"):
        relation_id = cur.u32()
        rel = state.relations.get(relation_id)
        if rel is None:
            raise ParseError(f"Delete for unknown relation_id {relation_id}")
        marker = cur.u8()
        if marker not in (ord("K"), ord("O")):
            raise ParseError(f"Delete missing 'K'/'O' old tuple (got {marker!r})")
        before = _parse_tuple(cur, rel)
        return ChangeEvent(
            op="D",
            relation_id=relation_id,
            schema_name=rel.schema_name,
            table_name=rel.table_name,
            lsn=state.current_lsn or "0/0",
            xid=state.current_xid or 0,
            commit_timestamp=state.current_commit_ts_iso,
            before=before,
            after=None,
        )
    if tag == ord("T"):
        relation_count = cur.u32()
        _flags = cur.u8()
        rel_ids = [cur.u32() for _ in range(relation_count)]
        state.unhandled_event_types.append("Truncate")
        # We still surface a ChangeEvent so the replayer can quarantine it
        # with the explicit op="T" classification — never silently dropped.
        first_id = rel_ids[0] if rel_ids else 0
        rel = state.relations.get(first_id)
        return ChangeEvent(
            op="T",
            relation_id=first_id,
            schema_name=rel.schema_name if rel else "",
            table_name=rel.table_name if rel else "",
            lsn=state.current_lsn or "0/0",
            xid=state.current_xid or 0,
            commit_timestamp=state.current_commit_ts_iso,
            before=None,
            after=None,
        )
    # Other tags: Y / O / M / S / streaming — count + skip.
    state.unhandled_event_types.append(chr(tag))
    return None


__all__ = [
    "ParseError",
    "parse_message",
    "_State",
    "_lsn_str",
    "_pg_ts_to_iso",
    "_UnchangedToast",
]
