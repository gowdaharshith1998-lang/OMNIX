"""Phase B4 — private Sigstore Rekor v2 transparency log integration.

For customers under DORA / EU AI Act Article 12 / CMMC 2.0 / CNSA 2.0, each
ML-DSA-65 signed receipt is uploaded to the customer's private Rekor v2
instance and an inclusion proof is embedded in the receipt envelope.

The customer's auditor receives an offline-verifiable audit-kit tarball.
"""
