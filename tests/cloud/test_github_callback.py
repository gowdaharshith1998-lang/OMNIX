"""GitHub callback emitter tests."""

from __future__ import annotations

import hashlib
import hmac
import json

from omnix.cloud.api.github_callback import (
    GithubJobComplete,
    GithubReplicatedUnit,
    emit_job_complete,
    sign_payload,
)


def _captured_transport(captures: list):
    def t(*, url: str, payload: bytes, signature: str):
        captures.append({"url": url, "payload": payload, "signature": signature})
        return {"status": 200}
    return t


def test_sign_payload_is_hmac_sha256_with_prefix():
    secret = "topsecret"
    payload = b'{"hello":"world"}'
    sig = sign_payload(payload, secret)
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert sig == expected


def test_emit_job_complete_canonical_payload_and_signature():
    captures = []
    job = GithubJobComplete(
        job_id="j-1", installation_id=42, repo="org/repo",
        units=[
            GithubReplicatedUnit(
                unit_id="u-1", source_path="Foo.java",
                target_path="src/main/java/Foo.java", target_language="java21",
                receipt_id="r-1",
                receipt_url="https://verify.axiomcontrol.systems/r/r-1",
                verifier_url="https://verify.axiomcontrol.systems/r/r-1",
                daikon_invariants_agreed=5, daikon_invariants_violated=0,
                scientist_mismatches=0, diffy_mismatches=0,
                generated_code="class Foo {}",
            )
        ],
    )
    res = emit_job_complete(target_url="https://app/example/webhooks/job-complete",
                            secret="secret", job=job, transport=_captured_transport(captures))
    assert res["status"] == 200
    assert len(captures) == 1
    payload = captures[0]["payload"]
    parsed = json.loads(payload)
    assert parsed["job_id"] == "j-1"
    assert parsed["units"][0]["target_language"] == "java21"
    expected_sig = sign_payload(payload, "secret")
    assert captures[0]["signature"] == expected_sig


def test_canonical_payload_is_sorted_and_minified():
    job = GithubJobComplete(job_id="j", installation_id=1, repo="o/r", units=[])
    canonical = job.to_canonical_json()
    # No spaces between separators
    assert b": " not in canonical
    assert b", " not in canonical
    # Keys sorted
    parsed = json.loads(canonical)
    assert list(parsed.keys()) == sorted(parsed.keys())
