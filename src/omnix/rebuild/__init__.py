"""OMNIX rebuild pipeline — analyze ↔ spec gen ↔ LLM dispatch ↔
gates 1-4 ↔ signed RebuildReceipt emission.

The package's public surface is intentionally small:

    omnix.rebuild.run(...) -> list[Path]
        Walk a project, dispatch one LLM call per node, run gates 1-4,
        write a signed RebuildReceipt per node to .omnix/receipts/rebuilds/<ts>/

    omnix.rebuild.RebuildOutput
        Filesystem layout describing where a receipt + its sidecars live.

Gate 5 (property-based) and gate 6 (behavioral equivalence) are emitted as
`skipped` with reason `gate_not_wired` until their M2 implementations land.
See `omnix.receipts.rebuild_receipt` for the honesty invariant enforcement.
"""

from omnix.rebuild.runner import RebuildOutput, run

__all__ = ["RebuildOutput", "run"]
