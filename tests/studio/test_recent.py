"""Tests for :mod:`src.studio.recent` with isolated ``OMNIX_STUDIO_OMNIX_DIR``."""

import json
from pathlib import Path

import pytest

from src.studio import recent


def test_recent_starts_empty(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g"))
    assert recent.list_recent() == []  # type: ignore[unreachable]  # noqa: E501


def test_add_recent_prepends(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g"))
    p = (tmp_path / "a" / "proj")  # noqa: E501
    p.mkdir(parents=True)  # noqa: E501
    (p / "x").write_text("x", encoding="utf-8")
    recent.add_recent(p)
    r = recent.list_recent()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert r and r[0]["path"]  # type: ignore[index, no-untyped-def, misc, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_add_recent_dedupes_existing_path(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g"))
    p = (tmp_path / "p")  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    p.mkdir()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    recent.add_recent(p)  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    recent.add_recent(p)  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    r = recent.list_recent()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert [x["path"] for x in r] == [str(p.resolve())]  # type: ignore[no-untyped-def, misc, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_add_recent_caps_at_10(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g"))
    for i in range(12):
        p = tmp_path / f"cap{i}"  # noqa: E501
        p.mkdir()  # noqa: E501
        recent.add_recent(p)  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    r = recent.list_recent()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert len(r) == 10  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_recent_persists_across_load(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "g2"  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(d))
    p = tmp_path / "persist"  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    p.mkdir()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    recent.add_recent(p)  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    got = (d / "recent.json")  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert got.is_file()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
    a = json.loads(got.read_text(encoding="utf-8"))  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-any-return, union-attr, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert a["version"] == 1  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    b = recent.list_recent()  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert b  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
