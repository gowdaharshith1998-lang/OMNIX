"""tus 1.0.0 conformance tests.

Covers:
  * OPTIONS pre-flight headers
  * POST create + Location header
  * PATCH append with correct offset
  * PATCH conflict on stale offset (resume protection)
  * HEAD returns updated offset (resume after disconnect)
  * Multi-chunk completion -> storage commit + sha256 sealed
  * DELETE drops a partial upload
  * Rejects Content-Type != application/offset+octet-stream
  * Honors Upload-Checksum
"""

from __future__ import annotations

import hashlib
from base64 import b64encode

import pytest
from fastapi.testclient import TestClient

from omnix.cloud.api.main import create_app
from omnix.cloud.auth.jwt_session import issue
from omnix.cloud.ingest.storage import MemoryStorage, get_storage, reset_storage_singleton


@pytest.fixture
def memory_storage():
    reset_storage_singleton()
    backend = MemoryStorage()
    get_storage(override=backend)
    yield backend
    reset_storage_singleton()


@pytest.fixture
def client(memory_storage):
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = issue("u-1", "tenant-1", "smb", "u@example.com")
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant-1"}


def test_tus_options_advertises_protocol(client):
    resp = client.options("/v1/upload/")
    assert resp.status_code == 204
    assert resp.headers["Tus-Resumable"] == "1.0.0"
    assert "creation" in resp.headers["Tus-Extension"]
    assert "termination" in resp.headers["Tus-Extension"]
    assert int(resp.headers["Tus-Max-Size"]) > 0


def test_tus_create_returns_location(client, auth_headers):
    resp = client.post(
        "/v1/upload/",
        headers={
            **auth_headers,
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "100",
            "Upload-Metadata": "filename " + b64encode(b"foo.tar").decode(),
        },
    )
    assert resp.status_code == 201
    assert resp.headers["Upload-Offset"] == "0"
    assert "/v1/upload/" in resp.headers["Location"]


def test_tus_full_lifecycle_seals_storage(client, memory_storage, auth_headers):
    payload = b"OMNIX-replicator-payload" * 200
    sha = hashlib.sha256(payload).hexdigest()

    resp = client.post(
        "/v1/upload/",
        headers={
            **auth_headers,
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(len(payload)),
            "Upload-Metadata": "filename " + b64encode(b"bundle.tar").decode(),
        },
    )
    assert resp.status_code == 201
    location = resp.headers["Location"]
    upload_id = location.rstrip("/").split("/")[-1]

    # Chunked PATCH in two halves to verify resume semantics.
    mid = len(payload) // 2
    r1 = client.patch(
        f"/v1/upload/{upload_id}",
        headers={
            "Tus-Resumable": "1.0.0",
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "0",
            **auth_headers,
        },
        content=payload[:mid],
    )
    assert r1.status_code == 204, r1.text
    assert int(r1.headers["Upload-Offset"]) == mid

    # HEAD probes resume offset
    rh = client.head(f"/v1/upload/{upload_id}", headers=auth_headers)
    assert rh.status_code == 200
    assert int(rh.headers["Upload-Offset"]) == mid

    # Resume final half
    r2 = client.patch(
        f"/v1/upload/{upload_id}",
        headers={
            "Tus-Resumable": "1.0.0",
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": str(mid),
            **auth_headers,
        },
        content=payload[mid:],
    )
    assert r2.status_code == 204
    assert int(r2.headers["Upload-Offset"]) == len(payload)
    assert r2.headers["Upload-Sha256"] == sha
    storage_key = r2.headers["X-Storage-Key"]
    assert storage_key.startswith("uploads/tenant-1/")

    # Sealed into storage
    stored = memory_storage.get_object(storage_key)
    assert stored == payload


def test_tus_rejects_stale_offset(client, auth_headers):
    resp = client.post(
        "/v1/upload/",
        headers={**auth_headers, "Upload-Length": "10"},
    )
    upload_id = resp.headers["Location"].rstrip("/").split("/")[-1]

    r = client.patch(
        f"/v1/upload/{upload_id}",
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "5",  # wrong
            **auth_headers,
        },
        content=b"hello",
    )
    assert r.status_code == 409


def test_tus_rejects_wrong_content_type(client, auth_headers):
    resp = client.post("/v1/upload/", headers={**auth_headers, "Upload-Length": "10"})
    upload_id = resp.headers["Location"].rstrip("/").split("/")[-1]

    r = client.patch(
        f"/v1/upload/{upload_id}",
        headers={**auth_headers, "Content-Type": "application/json", "Upload-Offset": "0"},
        content=b"hello",
    )
    assert r.status_code == 415


def test_tus_checksum_extension(client, auth_headers):
    payload = b"abc"
    digest = b64encode(hashlib.sha256(payload).digest()).decode()
    resp = client.post("/v1/upload/", headers={**auth_headers, "Upload-Length": str(len(payload))})
    upload_id = resp.headers["Location"].rstrip("/").split("/")[-1]
    r = client.patch(
        f"/v1/upload/{upload_id}",
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "0",
            "Upload-Checksum": f"sha256 {digest}",
            **auth_headers,
        },
        content=payload,
    )
    assert r.status_code == 204


def test_tus_checksum_mismatch_460(client, auth_headers):
    resp = client.post("/v1/upload/", headers={**auth_headers, "Upload-Length": "3"})
    upload_id = resp.headers["Location"].rstrip("/").split("/")[-1]
    bogus = b64encode(b"0" * 32).decode()
    r = client.patch(
        f"/v1/upload/{upload_id}",
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "0",
            "Upload-Checksum": f"sha256 {bogus}",
            **auth_headers,
        },
        content=b"abc",
    )
    assert r.status_code == 460


def test_tus_delete_terminates_upload(client, auth_headers):
    resp = client.post("/v1/upload/", headers={**auth_headers, "Upload-Length": "10"})
    upload_id = resp.headers["Location"].rstrip("/").split("/")[-1]
    r = client.delete(f"/v1/upload/{upload_id}", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.head(f"/v1/upload/{upload_id}", headers=auth_headers)
    assert r2.status_code == 404


def test_tus_create_requires_session(client):
    resp = client.post("/v1/upload/", headers={"Upload-Length": "10"})
    assert resp.status_code == 401


def test_tus_upload_rejects_cross_tenant_access(client, auth_headers):
    resp = client.post("/v1/upload/", headers={**auth_headers, "Upload-Length": "10"})
    upload_id = resp.headers["Location"].rstrip("/").split("/")[-1]
    other_token = issue("u-2", "tenant-2", "smb", "other@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}", "X-Tenant-Id": "tenant-2"}
    r = client.head(f"/v1/upload/{upload_id}", headers=other_headers)
    assert r.status_code == 403
