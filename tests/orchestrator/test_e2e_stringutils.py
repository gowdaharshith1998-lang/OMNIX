"""End-to-end orchestrator tripwire — StringUtils.java fixture.

This test is the integration gap between the orchestrator (Phase 5) and the
JVM-backed Java semantic emitter (Phase 6 dispatch). It is intentionally
marked xfail(strict=True) so:

  - it does NOT pass today (we haven't vendored the emitter JAR or shipped a
    StringUtils.java fixture),
  - it WILL flip to XPASS the moment Phase 6 lands, forcing a stand-up review
    instead of silently rotting.

When Phase 6 wires it up, the body below documents the expected assertions
exactly so the next implementer doesn't have to re-derive intent.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "needs JavaSemanticEmitter JAR vendored + StringUtils.java parsed "
        "into a real GraphStore — happens in M1 Phase 6 dispatch"
    ),
)
def test_orchestrator_walks_stringutils_methods_in_topo_order(tmp_path: Path) -> None:
    """Intended assertion (will be filled in by Phase 6):

      1. Drop the StringUtils.java fixture under tmp_path/src/.
      2. Run `omnix analyze` (or call the JavaSemanticEmitter directly) to
         produce tmp_path/.omnix/omnix.db with reverse/isEmpty/isBlank nodes.
      3. Call orchestrator.dispatcher.run with a stub dispatch_fn that
         returns the constant string "// rebuilt".
      4. Assert one RebuildAttempt per method (3 total).
      5. Assert dispatch order: leaf methods (isEmpty) before composite ones
         (isBlank/reverse if they depend on isEmpty).
      6. Assert every attempt's node_fqn ends in one of:
         'reverse', 'isEmpty', 'isBlank'.
    """
    from omnix.orchestrator.dispatcher import run

    # Placeholder: invocation will fail until the GraphStore is populated.
    attempts = run(tmp_path, target_language="java21", dispatch_fn=lambda p: "// rebuilt")
    suffixes = {a.node_fqn.rsplit(".", 1)[-1] for a in attempts}
    assert suffixes >= {"reverse", "isEmpty", "isBlank"}
