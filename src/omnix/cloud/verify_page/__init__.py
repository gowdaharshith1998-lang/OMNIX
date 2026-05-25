"""Public verifier page — the moat made visible.

Three endpoints (relative to /verify):
  GET  /r/{receipt_id}                     HTML — renders receipt + signature
  GET  /r/{receipt_id}.json                Raw receipt JSON
  GET  /r/{receipt_id}.sig                 Raw signature bytes
  GET  /pubkey                             Current ML-DSA-65 public key (raw)
  POST /api/verify                         Server-side verify (ML-DSA-65)

The HTML page loads a small JS bundle that performs the verify client-side
when a WASM verifier is present. When absent, the page falls back to
``POST /api/verify`` — the result is identical (same pure-Python verify
shipped in the core), but the client-side path is what gives independent
verifiability.
"""

from __future__ import annotations

from omnix.cloud.verify_page.app import app  # noqa: F401
