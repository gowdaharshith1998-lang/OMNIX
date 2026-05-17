"""omnix.gates — verification gates for rebuilt code.

M1 ships gates 1-4 (mechanical, deterministic):
- gate1_syntactic: parser dry-run
- gate2_typecheck: type/symbol resolution
- gate3_signature: signature matches spec
- gate4_dependency: dependency edges match spec

M2 will add gates 5-6:
- gate5_property: property-based testing (Hypothesis-Java)
- gate6_behavioral: dual-runtime equivalence harness
"""

from omnix.gates.errors import GateCrashError
from omnix.gates.result import GateError, GateResult

__all__ = ["GateCrashError", "GateError", "GateResult"]
