from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omnix_scientist import Experiment, jsonl_publisher, list_publisher


def test_agreement_returns_control_value():
    sink = []
    e = Experiment("e", publisher=list_publisher(sink))
    e.use(lambda x: x + 1)
    e.try_(lambda x: x + 1)
    assert e.run(5) == 6
    assert sink == []


def test_mismatch_recorded():
    sink = []
    e = Experiment("e", publisher=list_publisher(sink))
    e.use(lambda x: x + 1)
    e.try_(lambda x: x + 2)
    assert e.run(5) == 6
    assert len(sink) == 1
    assert sink[0].candidate.value == 7


def test_jsonl_publisher_appends(tmp_path):
    p = tmp_path / "out.jsonl"
    e = Experiment("e", publisher=jsonl_publisher(p))
    e.use(lambda x: x)
    e.try_(lambda x: x + 1)
    e.run(1)
    e.run(2)
    lines = p.read_text().splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["experiment"] == "e"


def test_enabled_gate_skips_candidate():
    sink = []
    e = Experiment("e", publisher=list_publisher(sink), enabled=lambda: False)
    e.use(lambda x: 1)
    e.try_(lambda x: 2)
    assert e.run(0) == 1
    assert sink == []
