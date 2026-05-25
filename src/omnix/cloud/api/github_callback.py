"""Shape A → Shape C job-complete callback.

When a job dispatched with ``mode="github-app"`` finishes, Shape A POSTs a
JSON payload to the GitHub App service's ``/webhooks/job-complete`` endpoint
with an HMAC-SHA256 signature in ``X-Omnix-Signature``.

This module exposes the *outbound* surface — it emits the webhook — and
mirror routes used by tests to verify the canonical payload shape.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

router = APIRouter()


@dataclass
class GithubReplicatedUnit:
    unit_id: str
    source_path: str
    target_path: str
    target_language: str
    receipt_id: str
    receipt_url: str
    verifier_url: str
    daikon_invariants_agreed: int = 0
    daikon_invariants_violated: int = 0
    scientist_mismatches: int = 0
    diffy_mismatches: int = 0
    generated_code: str = ""


@dataclass
class GithubJobComplete:
    job_id: str
    installation_id: int
    repo: str
    units: list[GithubReplicatedUnit] = field(default_factory=list)

    def to_canonical_json(self) -> bytes:
        return json.dumps(
            {
                "job_id": self.job_id,
                "installation_id": self.installation_id,
                "repo": self.repo,
                "units": [asdict(u) for u in self.units],
            },
            sort_keys=True, separators=(",", ":"),
        ).encode()


def sign_payload(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def emit_job_complete(
    *,
    target_url: str,
    secret: str,
    job: GithubJobComplete,
    transport=None,
) -> dict[str, Any]:
    """Send the webhook. ``transport`` is injectable for tests."""
    payload = job.to_canonical_json()
    signature = sign_payload(payload, secret)
    if transport is not None:
        return transport(url=target_url, payload=payload, signature=signature)

    import httpx
    resp = httpx.post(
        target_url,
        content=payload,
        headers={"X-Omnix-Signature": signature, "Content-Type": "application/json"},
        timeout=30,
    )
    return {"status": resp.status_code, "body": resp.text}


# ----- mirror endpoint (used by /v1/jobs/{id}/github/complete for tests) -----

class _UnitPayload(BaseModel):
    unit_id: str
    source_path: str
    target_path: str
    target_language: str
    receipt_id: str
    receipt_url: str
    verifier_url: str
    daikon_invariants_agreed: int = 0
    daikon_invariants_violated: int = 0
    scientist_mismatches: int = 0
    diffy_mismatches: int = 0
    generated_code: str = ""


class _JobCompletePayload(BaseModel):
    job_id: str
    installation_id: int
    repo: str
    units: list[_UnitPayload]
    target_url: str
    secret: str | None = None


@router.post("/github/emit", include_in_schema=False)
async def emit(body: _JobCompletePayload = Body(...)):
    """Test/dev mirror endpoint: emit a github callback to the supplied URL."""
    secret = body.secret or os.environ.get("OMNIX_GITHUB_APP_WEBHOOK_SECRET") or ""
    if not secret:
        raise HTTPException(status_code=400, detail="webhook secret required")
    job = GithubJobComplete(
        job_id=body.job_id,
        installation_id=body.installation_id,
        repo=body.repo,
        units=[GithubReplicatedUnit(**u.model_dump()) for u in body.units],
    )
    return emit_job_complete(
        target_url=body.target_url,
        secret=secret,
        job=job,
        transport=_record_only_transport,
    )


def _record_only_transport(*, url: str, payload: bytes, signature: str) -> dict[str, Any]:
    """Records the canonical payload + signature instead of issuing a network call.

    The test suite asserts on this output to verify the HMAC contract.
    """
    return {
        "url": url,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "signature": signature,
    }
