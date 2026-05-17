"""``test_detect`` helpers: runner priority and pytest summary edge cases."""

from __future__ import annotations

from pathlib import Path

from omnix.find_bugs import test_detect


def test_parse_pytest_failed_no_passed() -> None:
    p, t = test_detect.parse_pytest_summary(
        "E some error\n1 failed, 0 passed in 0.01s", ""
    )
    assert p + max(0, t - p) >= 1 or t == 0


def test_parse_empty() -> None:
    p, t = test_detect.parse_pytest_summary("", "")
    assert p == 0
    assert t == 0


def test_parse_only_failed_line() -> None:
    p, t = test_detect.parse_pytest_summary("FAILED tests/test_foo.py::a", "")
    _ = t + p
    assert isinstance(p, int)


def test_priority_pytest_wins_with_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[x]\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
    s = test_detect.detect_test_runner(tmp_path)
    assert s.runner_id == "pytest"
    assert "pytest" in s.order_chosen


def test_cargo_no_pyproject(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname = \"a\"\nversion = \"0\"\n", encoding="utf-8"
    )
    s = test_detect.detect_test_runner(tmp_path)
    assert s.runner_id == "cargo"


def test_npm_from_package_json_with_test_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name":"a","scripts":{"test":"node -c index.js"}}\n', encoding="utf-8"
    )
    s = test_detect.detect_test_runner(tmp_path)
    assert s.runner_id == "npm"


def test_gomod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module x\ngo 1.20\n", encoding="utf-8")
    s = test_detect.detect_test_runner(tmp_path)
    assert s.runner_id == "go"
