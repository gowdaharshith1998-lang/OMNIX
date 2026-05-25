"""Phase B3 — strangler-fig cutover orchestration.

Each traffic-shift is authorized by a fresh ML-DSA-65 signed receipt
attesting that the four Layer 5 verifiers were green at the new percentage.
Rollback is itself a signed event.
"""
