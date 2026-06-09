"""tus 1.0.0 protocol resumable-upload handler.

Implements:
  OPTIONS /     pre-flight: tus-version, tus-max-size, tus-extension
  POST    /     create:     reserves an upload, returns Location
  HEAD    /{id} status:     returns upload-offset
  PATCH   /{id} append:     extends data; idempotent via upload-offset header
  DELETE  /{id} terminate:  drops a partial upload

Storage:
  Resumable bytes live in OMNIX_TUS_DATA_DIR/<id>.part with a metadata sidecar.
  On final byte received (offset == upload-length), the file is sealed,
  its sha256 computed, and the artifact is committed to the configured
  storage backend (memory/R2/S3) under key uploads/{tenant_id}/{job_id}.tar.

We re-implement the protocol rather than relying on `tus-py-server` so that
we can integrate cleanly with our Tenant/Job model and run the full conformance
suite inside the cloud test directory.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from base64 import b64decode, b64encode
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from omnix.cloud.auth.tenancy import require_session_tenant
from omnix.cloud.config import get_settings
from omnix.cloud.ingest.storage import get_storage

TUS_VERSION = "1.0.0"
TUS_RESUMABLE = "1.0.0"
TUS_EXTENSIONS = (
    "creation",
    "creation-with-upload",
    "expiration",
    "termination",
    "checksum",
)


@dataclass
class UploadDescriptor:
    id: str
    length: int
    offset: int
    metadata: dict[str, str]
    tenant_id: str | None
    sha256: str | None = None
    committed: bool = False
    storage_key: str | None = None


def _data_dir() -> Path:
    p = Path(get_settings().tus_data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _part_path(upload_id: str) -> Path:
    return _data_dir() / f"{upload_id}.part"


def _meta_path(upload_id: str) -> Path:
    return _data_dir() / f"{upload_id}.json"


def _load(upload_id: str) -> UploadDescriptor:
    mp = _meta_path(upload_id)
    if not mp.exists():
        raise HTTPException(status_code=404, detail="upload not found")
    return UploadDescriptor(**json.loads(mp.read_text()))


def get_upload_metadata(upload_id: str) -> UploadDescriptor | None:
    """Public lookup: returns the descriptor or None when not found.

    Unlike ``_load`` this never raises — callers outside the tus router
    (e.g. POST /v1/jobs resolving an upload_id to a storage_key) need a
    plain Optional so they can decide their own HTTP semantics.
    """
    mp = _meta_path(upload_id)
    if not mp.exists():
        return None
    try:
        return UploadDescriptor(**json.loads(mp.read_text()))
    except Exception:  # noqa: BLE001 — corrupted metadata is treated as "not found"
        return None


def _save(desc: UploadDescriptor) -> None:
    _meta_path(desc.id).write_text(json.dumps(asdict(desc)))


def _parse_upload_metadata(raw: str | None) -> dict[str, str]:
    """tus Upload-Metadata is comma-separated `key b64value` pairs."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.split(" ", 1)
        if len(parts) == 1:
            out[parts[0]] = ""
        else:
            try:
                out[parts[0]] = b64decode(parts[1]).decode("utf-8")
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"bad Upload-Metadata token: {parts[0]}",
                ) from exc
    return out


def _encode_metadata(meta: dict[str, str]) -> str:
    out = []
    for k, v in meta.items():
        if v == "":
            out.append(k)
        else:
            out.append(f"{k} {b64encode(v.encode('utf-8')).decode('ascii')}")
    return ",".join(out)


def _verify_checksum(algo: str, expected_b64: str, payload: bytes) -> bool:
    if algo not in {"sha1", "sha256"}:
        raise HTTPException(status_code=400, detail=f"unsupported checksum: {algo}")
    digest = hashlib.new(algo, payload).digest()
    return secrets.compare_digest(b64decode(expected_b64), digest)


def _common_response_headers() -> dict[str, str]:
    return {
        "Tus-Resumable": TUS_RESUMABLE,
        "Tus-Version": TUS_VERSION,
        "Tus-Extension": ",".join(TUS_EXTENSIONS),
        "Cache-Control": "no-store",
    }


def _require_upload_owner(desc: UploadDescriptor) -> None:
    tenant_id = require_session_tenant()
    if desc.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="upload belongs to another tenant")


router = APIRouter()


@router.options("")
@router.options("/")
async def tus_options() -> Response:
    settings = get_settings()
    headers = _common_response_headers()
    headers["Tus-Max-Size"] = str(settings.tus_max_bytes)
    return Response(status_code=204, headers=headers)


@router.post("")
@router.post("/")
async def tus_create(
    request: Request,
    upload_length: int | None = Header(None, alias="Upload-Length"),
    upload_metadata: str | None = Header(None, alias="Upload-Metadata"),
    tus_resumable: str | None = Header(None, alias="Tus-Resumable"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    if tus_resumable and tus_resumable != TUS_RESUMABLE:
        raise HTTPException(status_code=412, detail="tus version mismatch")
    settings = get_settings()
    if upload_length is None:
        raise HTTPException(status_code=400, detail="Upload-Length required")
    if upload_length > settings.tus_max_bytes:
        raise HTTPException(status_code=413, detail="upload exceeds Tus-Max-Size")
    tenant_id = require_session_tenant(x_tenant_id)

    upload_id = uuid.uuid4().hex
    desc = UploadDescriptor(
        id=upload_id,
        length=upload_length,
        offset=0,
        metadata=_parse_upload_metadata(upload_metadata),
        tenant_id=tenant_id,
    )
    _part_path(upload_id).write_bytes(b"")
    _save(desc)

    base = str(request.url).rstrip("/")
    headers = _common_response_headers()
    headers["Location"] = f"{base}/{upload_id}"
    headers["Upload-Offset"] = "0"
    return Response(status_code=201, headers=headers)


@router.head("/{upload_id}")
async def tus_head(upload_id: str) -> Response:
    desc = _load(upload_id)
    _require_upload_owner(desc)
    headers = _common_response_headers()
    headers["Upload-Length"] = str(desc.length)
    headers["Upload-Offset"] = str(desc.offset)
    if desc.metadata:
        headers["Upload-Metadata"] = _encode_metadata(desc.metadata)
    return Response(status_code=200, headers=headers)


@router.patch("/{upload_id}")
async def tus_patch(
    upload_id: str,
    request: Request,
    upload_offset: int | None = Header(None, alias="Upload-Offset"),
    content_type: str | None = Header(None, alias="Content-Type"),
    upload_checksum: str | None = Header(None, alias="Upload-Checksum"),
):
    if content_type and content_type != "application/offset+octet-stream":
        raise HTTPException(status_code=415, detail="bad Content-Type")
    if upload_offset is None:
        raise HTTPException(status_code=400, detail="Upload-Offset required")

    desc = _load(upload_id)
    _require_upload_owner(desc)
    if upload_offset != desc.offset:
        raise HTTPException(status_code=409, detail="Upload-Offset mismatch")
    if desc.committed:
        raise HTTPException(status_code=410, detail="upload already finalized")

    payload = await request.body()
    if upload_checksum:
        algo, _, expected = upload_checksum.partition(" ")
        if not _verify_checksum(algo, expected, payload):
            raise HTTPException(status_code=460, detail="checksum mismatch")

    if desc.offset + len(payload) > desc.length:
        raise HTTPException(status_code=413, detail="offset exceeds Upload-Length")

    part = _part_path(upload_id)
    with part.open("ab") as f:
        f.write(payload)
    desc.offset += len(payload)

    if desc.offset == desc.length:
        data = part.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        backend = get_storage()
        tenant = desc.tenant_id or "anonymous"
        filename = desc.metadata.get("filename") or f"{desc.id}.tar"
        storage_key = f"uploads/{tenant}/{desc.id}/{filename}"
        backend.put_object(storage_key, data, sha256=digest)
        desc.sha256 = digest
        desc.committed = True
        desc.storage_key = storage_key
    _save(desc)

    headers = _common_response_headers()
    headers["Upload-Offset"] = str(desc.offset)
    if desc.committed:
        headers["Upload-Sha256"] = desc.sha256 or ""
        headers["X-Storage-Key"] = desc.storage_key or ""
    return Response(status_code=204, headers=headers)


@router.delete("/{upload_id}")
async def tus_delete(upload_id: str) -> Response:
    desc = _load(upload_id)
    _require_upload_owner(desc)
    mp = _meta_path(upload_id)
    pp = _part_path(upload_id)
    if not mp.exists():
        raise HTTPException(status_code=404, detail="upload not found")
    mp.unlink(missing_ok=True)
    pp.unlink(missing_ok=True)
    return Response(status_code=204, headers=_common_response_headers())


@router.get("/{upload_id}/status")
async def upload_status(upload_id: str) -> JSONResponse:
    desc = _load(upload_id)
    _require_upload_owner(desc)
    return JSONResponse(
        {
            "id": desc.id,
            "length": desc.length,
            "offset": desc.offset,
            "committed": desc.committed,
            "sha256": desc.sha256,
            "storage_key": desc.storage_key,
            "metadata": desc.metadata,
        }
    )


# Helper for callers (the JobService) to introspect a finished upload.
def get_upload(upload_id: str) -> UploadDescriptor:
    return _load(upload_id)
