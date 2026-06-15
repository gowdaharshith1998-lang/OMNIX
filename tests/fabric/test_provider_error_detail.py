# CLASSIFICATION: XFAIL-WITH-REASON — all 2 tests reference body_text response shape (slice 15.3.7 provider error detail not yet implemented)
from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from omnix.fabric.providers import openai_compatible
from tests.fabric import mocks

pytestmark = pytest.mark.xfail(
    strict=True,
    reason=(
        "slice 15.3.7 provider error detail not yet implemented: "
        "openai_compatible response dict lacks 'body_text' and 'body_json' fields on HTTP error. "
        "Test is the spec; lands when slice 15.3.7 backend wires the new error shape. "
        "Tracked as a known pre-M1 limitation (provider-error-detail). "
        "[Outside M1 finisher Phase 4-7 scope — separate slice-15.3.7 work stream.]"
    ),
)


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
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


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
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

