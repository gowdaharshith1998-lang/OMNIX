"""WebSocket message serialization (Studio)."""
from __future__ import annotations

import pytest

from src.studio.ws_protocol import WsError, msg_bootstrap_start, msg_node_added, validate_serialized
from src.studio import ws_protocol as wsp


def test_bootstrap_start_serializes() -> None:  # noqa: D103
    m: dict = msg_bootstrap_start(  # type: ignore[assignment, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
        "w1", 3, "existing"  # type: ignore[no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    )
    assert m["type"] == "bootstrap_start"  # type: ignore[no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    assert wsp.validate_serialized(m, from_server=True) == "bootstrap_start"  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_node_added_serializes() -> None:  # noqa: D103
    m = msg_node_added(  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        {"id": "x", "name": "n", "type": "function", "file_path": "a.py", "line_start": 1, "line_end": 2, "metadata": {}}  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    )
    assert wsp.validate_serialized(m, from_server=True) == "node_added"  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501


def test_invalid_type_raises() -> None:  # noqa: D103
    with pytest.raises(WsError):  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        validate_serialized({"ts": 1, "nope": 1}, from_server=True)  # type: ignore[unreachable, union-attr, misc, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
    with pytest.raises(WsError):  # noqa: E501
        validate_serialized(  # noqa: E501
            {"type": "not_a_real_omnix_message_type_12345", "ts": 1.0},
            from_server=True,  # noqa: E501
        )
