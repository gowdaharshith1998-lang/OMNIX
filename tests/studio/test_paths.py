from pathlib import Path

from src.studio.paths import ensure_global_omnix_dir, ensure_project_omnix_dir


def test_global_omnix_dir_creates_if_missing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: D103, E501
    g = tmp_path / "g"
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(g))
    d = ensure_global_omnix_dir()  # noqa: E501
    assert d == g.resolve()  # noqa: E501
    assert d.is_dir()  # noqa: E501


def test_project_omnix_dir_creates_if_missing(tmp_path: Path) -> None:  # noqa: D103
    p = tmp_path / "proj"  # noqa: E501
    p.mkdir()  # noqa: E501, E501
    d = ensure_project_omnix_dir(p)  # noqa: E501
    assert d == p / ".omnix"  # noqa: E501, E501, E501
    assert d.is_dir()  # noqa: E501, E501, E501
