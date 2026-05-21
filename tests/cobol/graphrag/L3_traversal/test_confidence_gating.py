from __future__ import annotations

from omnix.traversal.confidence import parse_sufficient_signal, should_grant_extra_hop


def test_below_threshold_confidence_gets_extra_hop() -> None:
    signal = parse_sufficient_signal('{"sufficient": true, "confidence": 0.5}')
    assert signal is not None
    assert should_grant_extra_hop(signal)
