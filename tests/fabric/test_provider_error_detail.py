from __future__ import annotations

from typing import Any
from unittest import mock

from omnix.fabric.providers import openai_compatible
from tests.fabric import mocks


@mock.patch("fabric.providers.common.urllib.request.urlopen")
def test_adapter_populates_body_text_and_json_on_http_error(m_url: Any) -> None:
    m_url.side_effect = mocks.http_error(
        401, '{"error":{"message":"Incorrect API key provided","code":"invalid_api_key"}}'
    )
    status, data = openai_compatible.call(
        model="gpt-test",
        api_key="bad",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10,
        timeout_s=1,
    )
    out = openai_compatible.normalize_response(status, data)

    assert out["error"] is True
    assert out["raw_response"]["status"] == 401
    assert "Incorrect API key" in out["raw_response"]["body_text"]
    assert out["raw_response"]["body_json"]["error"]["code"] == "invalid_api_key"


@mock.patch("fabric.providers.common.urllib.request.urlopen")
def test_adapter_truncates_error_body_text(m_url: Any) -> None:
    m_url.side_effect = mocks.http_error(500, "x" * 2500)
    status, data = openai_compatible.call(
        model="gpt-test",
        api_key="bad",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10,
        timeout_s=1,
    )
    out = openai_compatible.normalize_response(status, data)

    assert len(out["raw_response"]["body_text"]) == 2000
    assert out["raw_response"]["body_json"] is None

