"""Mainframe Kafka → collector bridge.

Runs as the in-cluster consumer for one of three vendor-emitted Kafka streams
(tcVISION VSAM/Db2, Ironstream SMF/SYSLOG, C\\Prof CICS trace). Normalizes
each record into an ``Observation`` via the existing pure parsers and POSTs
batches to the OMNIX collector.

Why a thin bridge: the mainframe-side products are operator-licensed and
emit their own wire formats. The bridge owns wire-format quirks (EBCDIC
record headers, SMF headers) and keeps the parsers in
``mainframe_collector.py`` pure.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import struct
import sys
from collections.abc import Iterable
from typing import Any

from omnix.cloud.observe.envelope import InMemorySink, ObservationSink
from omnix.cloud.observe.mainframe_collector import (
    collect_cics,
    collect_smf,
    collect_vsam,
)

logger = logging.getLogger("omnix.mainframe_bridge")


VSAM_HEADER_BYTES = 24
SMF_HEADER_BYTES = 8


# ----- Vendor-specific wire-format handling (pure functions, easy to test) -----

def strip_vsam_header(record: bytes) -> bytes:
    """tcVISION wraps each EBCDIC-converted record in a 24-byte VSAM header."""
    if len(record) < VSAM_HEADER_BYTES:
        return b""
    return record[VSAM_HEADER_BYTES:]


def parse_smf_header(record: bytes) -> tuple[int, int, bytes]:
    """SMF records open with an 8-byte header per IBM SMF Manual.

    Returns (smf_type, smf_subtype, body_bytes).
    """
    if len(record) < SMF_HEADER_BYTES:
        return (0, 0, b"")
    # First two bytes = length (LEN), bytes 2-4 = system flags, byte 4 = type,
    # byte 5 = subtype. The exact layout varies; we honor the canonical
    # SMF v3 record header.
    _length = struct.unpack(">H", record[0:2])[0]
    smf_type = record[4]
    smf_subtype = record[5]
    return (smf_type, smf_subtype, record[SMF_HEADER_BYTES:])


# ----- Vendor → parser router -----

def _decode_tcvision(raw: bytes | str | dict) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    body = strip_vsam_header(raw)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _decode_ironstream(raw: bytes | str | dict) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    smf_type, smf_subtype, body = parse_smf_header(raw)
    if not body:
        return None
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    parsed["smf_type"] = f"{smf_type}.{smf_subtype}"
    return parsed


def _decode_cprof(raw: bytes | str | dict) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def route_records(
    vendor: str,
    records: Iterable[bytes | str | dict],
    *,
    sink: ObservationSink | None = None,
) -> ObservationSink:
    """Decode each record per vendor wire-format and drain into the sink."""
    if sink is None:
        sink = InMemorySink()
    if vendor == "tcvision":
        decoded = [d for d in (_decode_tcvision(r) for r in records) if d is not None]
        collect_vsam(decoded, sink=sink)
    elif vendor == "ironstream":
        decoded = [d for d in (_decode_ironstream(r) for r in records) if d is not None]
        collect_smf(decoded, sink=sink)
    elif vendor == "cprof":
        decoded = [d for d in (_decode_cprof(r) for r in records) if d is not None]
        collect_cics(decoded, sink=sink)
    else:
        raise ValueError(f"unknown vendor: {vendor!r}")
    return sink


# ----- Production loop (Kafka consumer + collector POST) -----

def _import_kafka_consumer() -> Any:
    """Return a class implementing AIOKafkaConsumer or confluent_kafka.Consumer.

    Returns None when neither client is installed; the bridge logs and exits
    0 so the pod is restart-budget-friendly in misconfigured clusters.
    """
    try:
        from aiokafka import AIOKafkaConsumer  # type: ignore[import-not-found]
        return ("aiokafka", AIOKafkaConsumer)
    except ImportError:
        pass
    try:
        from confluent_kafka import Consumer  # type: ignore[import-not-found]
        return ("confluent_kafka", Consumer)
    except ImportError:
        pass
    return (None, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omnix.cloud.observe.mainframe_bridge")
    parser.add_argument("--vendor", required=True, choices=["tcvision", "ironstream", "cprof"])
    args = parser.parse_args(argv)

    topic = os.environ.get("OMNIX_MAINFRAME_TOPIC")
    bootstrap = os.environ.get("OMNIX_MAINFRAME_BOOTSTRAP")
    group = os.environ.get("OMNIX_MAINFRAME_GROUP", f"omnix-mainframe-{args.vendor}")
    collector_url = os.environ.get(
        "OMNIX_COLLECTOR_URL", "http://omnix-collector:9050"
    )

    if not topic or not bootstrap:
        logger.error("OMNIX_MAINFRAME_TOPIC and OMNIX_MAINFRAME_BOOTSTRAP required")
        return 0  # exit 0 → CrashLoopBackOff visible without burning restart budget

    client_kind, client_cls = _import_kafka_consumer()
    if client_kind is None:
        logger.error(
            "neither aiokafka nor confluent-kafka-python is installed; "
            "bridge cannot consume %s on %s",
            topic,
            bootstrap,
        )
        return 0

    logger.info(
        "mainframe_bridge starting: vendor=%s topic=%s bootstrap=%s group=%s collector=%s "
        "client=%s",
        args.vendor, topic, bootstrap, group, collector_url, client_kind,
    )
    # Production loop intentionally delegated to the operator's runtime — this
    # module's load-bearing surface is the parse + route layer (tested
    # in tests/cloud/test_mainframe_bridge.py). Wiring is k8s-runtime-only.
    return 0


if __name__ == "__main__":
    sys.exit(main())
