"""Pass 1: Identity — map SemanticNode -> Identity.

Pure mapping, no inference. Lifts FQN, kind, and source coordinates out of the
node so downstream passes (and the orchestrator) don't need to touch the raw
semantic node directly.
"""

from __future__ import annotations

from omnix.semantic import SemanticNode
from omnix.spec import Identity


def run(node: SemanticNode) -> Identity:
    """Project SemanticNode coordinates into an Identity record.

    Pure function: no side effects, no I/O.
    """
    return Identity(
        fqn=node.fqn,
        kind=node.kind,
        source_file=node.source_location.file_path,
        source_line=node.source_location.line,
    )
