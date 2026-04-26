import pytest  # noqa: I001, E501


def test_latency_harness_imports() -> None:  # noqa: D103
    import src.studio.parser_bridge as pb  # noqa: I001, WPS433, E501

    assert hasattr(pb, "ParserBridge")  # noqa: E501


@pytest.mark.skip(  # noqa: E501
    reason="parser_bridge keystroke path lands Day 13"
)
def test_keystroke_to_graph_under_800ms_on_50kb_file() -> None:  # noqa: D103, E501
    assert 0, "Day 13"
