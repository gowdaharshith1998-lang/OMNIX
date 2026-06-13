from __future__ import annotations

from omnix.agents.tools import OmnixTools


def test_read_file_rejects_parent_traversal(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    result = OmnixTools(str(project)).read_file("../secret.txt")

    assert "error" in result
    assert "outside project" in str(result["error"])


def test_read_file_accepts_project_relative_file(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "ok.py").write_text("print('ok')\n", encoding="utf-8")

    result = OmnixTools(str(project)).read_file("ok.py")

    assert result["file"] == "ok.py"
    assert "print('ok')" in str(result["content"])
