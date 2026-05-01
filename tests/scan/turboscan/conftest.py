"""Fixtures for TURBOSCAN tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def omnix_repo_path() -> Path:
    return Path(__file__).resolve().parents[3]
