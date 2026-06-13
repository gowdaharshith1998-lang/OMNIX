from __future__ import annotations

import pytest
from fastapi import HTTPException

from omnix.studio.security import safe_workspace_file_path


def test_workspace_file_path_rejects_parent_traversal(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(HTTPException):
        safe_workspace_file_path(project, "../escape.txt")
    assert not (tmp_path / "escape.txt").exists()


def test_workspace_file_path_accepts_project_relative_path(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    path, rel = safe_workspace_file_path(project, "src/app.py")

    assert path == (project / "src" / "app.py").resolve()
    assert rel == "src/app.py"
