from __future__ import annotations

import os
import shutil
import sysconfig
from pathlib import Path

import pytest

_ORIGINAL_PATH_HOME = Path.home

_JAVA_REQUIRED_NODEIDS = (
    "tests/semantic/java/test_parse_file.py",
    "tests/corpus/test_commons_lang_corpus.py",
    "tests/orchestrator/test_e2e_stringutils.py",
    "tests/orchestrator/test_dispatcher.py::test_e2e_with_real_graph_store",
    "tests/gates/test_gate1_syntactic.py::test_real_parser_catches_syntax_error_in_method_body",
)


def _pytest_home(cls: type[Path]) -> Path:
    raw = os.environ.get("OMNIX_HOME") or os.environ.get("HOME")
    if raw:
        return cls(raw).expanduser()
    return _ORIGINAL_PATH_HOME()


def pytest_configure() -> None:
    Path.home = classmethod(_pytest_home)  # type: ignore[method-assign]
    scripts_dir = Path(sysconfig.get_path("scripts"))
    if scripts_dir.is_dir():
        os.environ["PATH"] = str(scripts_dir) + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if shutil.which("java") is not None:
        return
    skip_java = pytest.mark.skip(reason="java executable not available on PATH")
    for item in items:
        nodeid = item.nodeid.replace("\\", "/")
        if any(required in nodeid for required in _JAVA_REQUIRED_NODEIDS):
            item.add_marker(skip_java)
