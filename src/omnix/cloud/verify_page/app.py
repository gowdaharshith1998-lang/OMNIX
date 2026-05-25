"""FastAPI sub-app for the public verifier."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from omnix.cloud.verify_page.store import (
    ReceiptDescriptor,
    get_receipt_store,
)

app = FastAPI(title="OMNIX Public Verifier", docs_url=None, redoc_url=None)

_TEMPLATE = (Path(__file__).parent / "templates" / "receipt.html").read_text(encoding="utf-8")


def _render(desc: ReceiptDescriptor) -> str:
    pubkey_b64 = base64.b64encode(desc.public_key).decode("ascii")
    sig_b64 = base64.b64encode(desc.signature).decode("ascii")
    payload_str = json.dumps(desc.payload, indent=2, sort_keys=True)
    return (
        _TEMPLATE.replace("{{RECEIPT_ID}}", desc.receipt_id)
        .replace("{{JOB_ID}}", desc.job_id)
        .replace("{{KIND}}", desc.receipt_kind)
        .replace("{{CREATED_AT}}", desc.created_at)
        .replace("{{SHA256}}", desc.payload_sha256)
        .replace("{{PUBKEY_B64}}", pubkey_b64)
        .replace("{{SIG_B64}}", sig_b64)
        .replace("{{PAYLOAD_JSON}}", payload_str)
    )


@app.get("/r/{receipt_id}.json")
async def receipt_json(receipt_id: str):
    desc = get_receipt_store().get(receipt_id)
    if desc is None:
        raise HTTPException(status_code=404, detail="receipt not found")
    return JSONResponse(desc.payload)


@app.get("/r/{receipt_id}.sig")
async def receipt_sig(receipt_id: str):
    desc = get_receipt_store().get(receipt_id)
    if desc is None:
        raise HTTPException(status_code=404, detail="receipt not found")
    return Response(desc.signature, media_type="application/octet-stream")


@app.get("/r/{receipt_id}", response_class=HTMLResponse)
async def render_receipt(receipt_id: str):
    desc = get_receipt_store().get(receipt_id)
    if desc is None:
        raise HTTPException(status_code=404, detail="receipt not found")
    return HTMLResponse(_render(desc))


@app.get("/pubkey/{receipt_id}")
async def pubkey(receipt_id: str):
    desc = get_receipt_store().get(receipt_id)
    if desc is None:
        raise HTTPException(status_code=404, detail="receipt not found")
    return Response(desc.public_key, media_type="application/octet-stream")


class VerifyRequest(BaseModel):
    payload_canonical_b64: str
    signature_b64: str
    public_key_b64: str
    ctx_b64: str = ""


class VerifyResponse(BaseModel):
    valid: bool
    sha256: str


@app.post("/api/verify", response_model=VerifyResponse)
async def api_verify(payload: Annotated[VerifyRequest, Body(...)]):
    try:
        msg = base64.b64decode(payload.payload_canonical_b64)
        sig = base64.b64decode(payload.signature_b64)
        pk = base64.b64decode(payload.public_key_b64)
        ctx = base64.b64decode(payload.ctx_b64) if payload.ctx_b64 else b""
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"bad base64: {exc}") from exc
    try:
        from omnix.receipts.verify import verify_bytes
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"verify module missing: {exc}") from exc
    valid = bool(verify_bytes(pk, msg, ctx, sig))
    return VerifyResponse(valid=valid, sha256=hashlib.sha256(msg).hexdigest())


@app.get("/wasm/verify.js", response_class=PlainTextResponse)
async def wasm_loader():
    """Returns the client-side verifier loader.

    The loader prefers the in-bundle WASM verifier; when absent (default
    in this scaffold), it falls back to the server endpoint.
    """
    return (Path(__file__).parent / "templates" / "verify.js").read_text()
