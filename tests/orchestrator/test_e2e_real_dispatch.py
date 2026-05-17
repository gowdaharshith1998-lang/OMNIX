"""E2E integration test: real LLM call through the orchestrator's
production dispatch_fn (`omnix.orchestrator.dispatcher._default_dispatch_fn`).

Gated by `OMNIX_REAL_LLM=1` to prevent accidental cost on CI / local
`pytest tests/` runs. The single test sends a trivial 3-line Java method
and asserts the response is non-empty + contains the method name.

Budget:
  - Wall-clock: <60 seconds
  - Spend: <~$0.50 (Opus 4.7 pricing at ~500 input + ~500 output tokens)

Pre-requisites for the gated path to succeed:
  - At least one Anthropic key registered in the Provider Fabric vault
    (BYOK UI, or `omnix axiom keygen` for project-scoped keys).
  - Network reachable.

The test does NOT cache responses — every run is a fresh API call. This
is intentional; cached "demos" defeat the point of demonstrating real
dispatch.
"""

from __future__ import annotations

import os
import time

import pytest

REAL_LLM = pytest.mark.skipif(
    not os.getenv("OMNIX_REAL_LLM"),
    reason="real-LLM gated; set OMNIX_REAL_LLM=1 to run (~$0.05-0.50 per run)",
)


@REAL_LLM
def test_default_dispatch_fn_hits_real_llm_for_trivial_prompt() -> None:
    from omnix.orchestrator.dispatcher import _default_dispatch_fn

    prompt = (
        "Output the following Java source verbatim with no commentary, "
        "no markdown fences:\n\n"
        "public class T {\n"
        '    public String greet(String name) {\n'
        '        return "Hi, " + name;\n'
        "    }\n"
        "}\n"
    )
    start = time.monotonic()
    response = _default_dispatch_fn(prompt, model="claude-opus-4.7")
    elapsed = time.monotonic() - start

    assert elapsed < 60, f"LLM dispatch took {elapsed:.1f}s, expected <60s"
    assert isinstance(response, str), f"response is {type(response).__name__}, expected str"
    assert response, "empty response from LLM"
    assert "greet" in response, (
        f"response missing method name 'greet'. First 200 chars:\n{response[:200]!r}"
    )

    # Print evidence so the operator can eyeball the model's output without
    # `-v` noise (pytest captures stdout but releases on test pass when `-s`).
    print("\n=== R-4.4 evidence ===")
    print(f"  wall-clock:    {elapsed:.1f}s")
    print(f"  response len:  {len(response)} chars")
    print(f"  response head: {response[:200]!r}")
