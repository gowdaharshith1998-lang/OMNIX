"""Tests for omnix.orchestrator.attempt — RebuildAttempt + sha256_hex.

Round-trip determinism is load-bearing for receipt signing; the frozen-ness
test guards against accidental in-place mutation by future code.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from omnix.orchestrator import RebuildAttempt, sha256_hex


def test_sha256_hex_deterministic() -> None:
    one = sha256_hex("the quick brown fox")
    two = sha256_hex("the quick brown fox")
    three = sha256_hex("the quick brown FOX")  # different input
    assert one == two
    assert one != three
    assert len(one) == 64


def test_rebuild_attempt_round_trip() -> None:
    original = RebuildAttempt(
        node_fqn="com.example.Foo.bar",
        spec_hash="a" * 64,
        prompt_template_version="v1-2026-05-17",
        prompt_text_hash="b" * 64,
        response_text="public static String bar(String s) { return s; }",
        timestamp=datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc),
        model="claude-opus-4.7",
    )
    d = original.to_dict()
    restored = RebuildAttempt.from_dict(d)
    assert restored == original


def test_rebuild_attempt_is_frozen() -> None:
    attempt = RebuildAttempt(
        node_fqn="x",
        spec_hash="a" * 64,
        prompt_template_version="v1-2026-05-17",
        prompt_text_hash="b" * 64,
        response_text="",
        timestamp=datetime(2026, 5, 17, tzinfo=timezone.utc),
        model="m",
    )
    with pytest.raises(FrozenInstanceError):
        attempt.node_fqn = "y"  # type: ignore[misc]


def test_rebuild_attempt_now_utc_is_timezone_aware() -> None:
    ts = RebuildAttempt.now_utc()
    assert ts.tzinfo is not None
    assert ts.tzinfo.utcoffset(ts) == timezone.utc.utcoffset(ts)


def test_rebuild_attempt_default_attempt_number_is_one() -> None:
    attempt = RebuildAttempt(
        node_fqn="x",
        spec_hash="a" * 64,
        prompt_template_version="v1-2026-05-17",
        prompt_text_hash="b" * 64,
        response_text="",
        timestamp=datetime(2026, 5, 17, tzinfo=timezone.utc),
        model="m",
    )
    assert attempt.attempt_number == 1
