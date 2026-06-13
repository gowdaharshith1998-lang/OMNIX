"""Oracle + MySQL adapter stub tests (P9)."""

from __future__ import annotations

import pytest

from omnix.dm.d5_change_data_capture.cdc_core import (
    NotYetImplementedInPRC,
    _eager_import_adapters,
    get_adapter,
)
from omnix.dm.d5_change_data_capture.mysql_adapter import MySQLAdapter
from omnix.dm.d5_change_data_capture.oracle_adapter import OracleAdapter


@pytest.fixture(autouse=True)
def _register():
    _eager_import_adapters()


def test_oracle_adapter_start_raises_with_pr_d_reference():
    a = OracleAdapter("oracle://x")
    with pytest.raises(NotYetImplementedInPRC) as exc:
        list(a.start("slot", "pub"))
    assert "PR D" in str(exc.value)


def test_mysql_adapter_start_raises_with_pr_d_reference():
    a = MySQLAdapter("mysql://x")
    with pytest.raises(NotYetImplementedInPRC) as exc:
        list(a.start("slot", "pub"))
    assert "PR D" in str(exc.value)


def test_registry_returns_oracle_adapter_for_oracle_dialect():
    assert isinstance(get_adapter("oracle", "x"), OracleAdapter)


def test_registry_returns_mysql_adapter_for_mysql_dialect():
    assert isinstance(get_adapter("mysql", "x"), MySQLAdapter)
