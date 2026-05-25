"""Tests for the mainframe bridge wire-format decoders + vendor routing."""

from __future__ import annotations

import json
import struct

import pytest

from omnix.cloud.observe.envelope import InMemorySink, ObservationKind
from omnix.cloud.observe.mainframe_bridge import (
    parse_smf_header,
    route_records,
    strip_vsam_header,
)


def _make_vsam_record(body: dict) -> bytes:
    header = b"\x00" * 24  # synthetic VSAM record header
    return header + json.dumps(body).encode("utf-8")


def _make_smf_record(smf_type: int, smf_subtype: int, body: dict) -> bytes:
    payload = json.dumps(body).encode("utf-8")
    length = len(payload) + 8
    # SMF v3 header: 2 bytes length, 2 bytes flags, 1 byte type, 1 byte subtype, 2 bytes reserved
    header = struct.pack(">HHBBH", length, 0, smf_type, smf_subtype, 0)
    return header + payload


def test_strip_vsam_header_drops_first_24_bytes() -> None:
    body = b'{"system_id":"SYS1","dataset":"PAYROLL.MASTER"}'
    record = b"\x00" * 24 + body
    assert strip_vsam_header(record) == body


def test_strip_vsam_header_too_short_returns_empty() -> None:
    assert strip_vsam_header(b"\x00" * 10) == b""


def test_parse_smf_header_extracts_type_subtype() -> None:
    record = _make_smf_record(30, 4, {"system_id": "SYS1", "job_name": "PAYROLL"})
    smf_type, smf_subtype, body = parse_smf_header(record)
    assert (smf_type, smf_subtype) == (30, 4)
    assert b"PAYROLL" in body


def test_route_tcvision_strips_header_and_routes_to_collect_vsam() -> None:
    sink = InMemorySink()
    rec = _make_vsam_record({"system_id": "SYS1", "dataset": "PAYROLL.MASTER"})
    route_records("tcvision", [rec], sink=sink)
    obs = sink.drain()
    assert len(obs) == 1
    assert obs[0].kind == ObservationKind.MAINFRAME_VSAM_OP
    assert obs[0].service == "PAYROLL.MASTER"
    assert obs[0].node == "SYS1"


def test_route_ironstream_strips_smf_header_and_tags_type() -> None:
    sink = InMemorySink()
    rec = _make_smf_record(30, 4, {"system_id": "SYS1", "job_name": "PAYROLL"})
    route_records("ironstream", [rec], sink=sink)
    obs = sink.drain()
    # collect_smf filters by smf_type == "30.4"; the bridge tags it after header parse.
    assert len(obs) == 1
    assert obs[0].kind == ObservationKind.MAINFRAME_JCL_JOB
    assert obs[0].service == "PAYROLL"


def test_route_cprof_consumes_jsonline_records() -> None:
    sink = InMemorySink()
    rec = json.dumps({"region": "CICSREG1", "transaction_id": "PAY1"})
    route_records("cprof", [rec], sink=sink)
    obs = sink.drain()
    assert len(obs) == 1
    assert obs[0].kind == ObservationKind.MAINFRAME_CICS_TXN
    assert obs[0].service == "PAY1"


def test_route_dict_records_passthrough() -> None:
    """When the bridge receives already-decoded dicts (test fixture or
    deserialized in-memory message), it should still route correctly."""
    sink = InMemorySink()
    route_records("cprof", [{"region": "R1", "transaction_id": "T1"}], sink=sink)
    assert sink.drain()[0].service == "T1"


def test_route_unknown_vendor_raises() -> None:
    with pytest.raises(ValueError):
        route_records("nonsense", [{}])
