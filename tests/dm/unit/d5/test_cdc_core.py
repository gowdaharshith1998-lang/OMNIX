"""D5 CDC core + adapter registry tests."""

from __future__ import annotations

import pytest

from omnix.dm.d5_change_data_capture.cdc_core import (
    NotYetImplementedInPRC,
    UnsupportedCDCDialect,
    _eager_import_adapters,
    get_adapter,
    register_adapter,
)


@pytest.fixture(autouse=True)
def _register():
    _eager_import_adapters()


def test_registered_adapter_returns_instance():
    adapter = get_adapter("oracle", "dsn://x")
    assert adapter is not None


def test_unknown_dialect_raises():
    with pytest.raises(UnsupportedCDCDialect):
        get_adapter("cassandra", "dsn://x")


def test_oracle_stub_raises_on_start():
    adapter = get_adapter("oracle", "dsn://x")
    with pytest.raises(NotYetImplementedInPRC) as exc:
        list(adapter.start("slot", "pub"))
    assert "PR D" in str(exc.value)


def test_mysql_stub_raises_on_start():
    adapter = get_adapter("mysql", "dsn://x")
    with pytest.raises(NotYetImplementedInPRC) as exc:
        list(adapter.start("slot", "pub"))
    assert "PR D" in str(exc.value)


def test_custom_adapter_can_be_registered():
    class _Dummy:
        def __init__(self, dsn):
            self.dsn = dsn

        def start(self, slot_name, publication_name):
            return iter([])

    register_adapter("dummy", _Dummy)
    a = get_adapter("dummy", "x")
    assert list(a.start("s", "p")) == []
