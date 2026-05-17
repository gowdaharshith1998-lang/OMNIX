"""Phase 3a/3b: v2 path matches v1 when :func:`load_profile` has nothing to load."""

from __future__ import annotations

import pytest

from omnix.parser.quality import QualityInputs, compute_score, compute_score_v2


def test_v2_falls_back_to_v1_when_no_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("omnix.parser.quality.load_profile", lambda _g, **_: None)
    samples = [
        QualityInputs(0, 0, 0, 0, 0, ()),
        QualityInputs(2, 1, 1, 3, 100, ("foo", "Bar")),
        QualityInputs(1, 0, 0, 0, 5, ("real_name",)),
    ]
    for qi in samples:
        assert compute_score(qi) == compute_score_v2(qi, "python")
    assert compute_score_v2(
        samples[0], "typescript"
    ) == compute_score(samples[0])
