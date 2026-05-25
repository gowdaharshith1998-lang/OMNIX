"""Compliance integrations — Drata + future Vanta/SecureFrame surfaces.

Each provider exposes a uniform ``push_evidence(receipts, controls)``
interface so Shape A can broadcast to multiple compliance vendors without
the audit logic knowing about any of them.
"""
