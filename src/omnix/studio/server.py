"""FastAPI Studio server: REST, WebSocket, static SPA (production)."""

from __future__ import annotations

import logging
import os

if os.environ.get("OMNIX_STUDIO_DEBUG") == "1":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s", force=True
    )
    for _noisy in ("watchdog", "watchdog.observers", "watchdog.observers.inotify_buffer"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    logging.getLogger("omnix.studio").setLevel(logging.DEBUG)
    _pb = logging.getLogger("omnix.studio.parser_bridge")
    _pb.setLevel(logging.INFO)
    if not _pb.handlers:
        _pb_h = logging.StreamHandler()
        _pb_h.setLevel(logging.INFO)
        _pb_h.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        _pb.addHandler(_pb_h)
        _pb.propagate = False

import asyncio
import contextlib
import json
import subprocess
import sys
import time
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

import sqlite3
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from omnix.graph.store import GraphStore, NodeRow
from omnix.parser import evolution
from omnix.parser.grammar_detect import detect_for_path
from omnix.parser.grammar_status_query import (
    collect_grammar_status,
    collect_mutations,
    collect_unknown_extensions,
    open_readonly,
    read_llm_budget_state,
    resolve_db_path,
    utc_now_iso,
)
from omnix.parser.ingest_dispatch import ingest_unified_codebase
from omnix.axiom.finding_receipt import compute_project_id
from omnix.find_bugs.receipt_emitter import verify_scan_directory
from omnix.omnix_version import __version__
from omnix.studio.bugs_scan import run_scan_for_workspace
from omnix.studio.parser_bridge import ParserBridge, broadcast_to_workspace
from omnix.studio.recent import add_recent, list_recent
from omnix.studio.watcher import ProjectWatcher
from omnix.studio.workspace import (
    MANAGER,
    Workspace,
    node_row_to_dict,
    open_workspace,
)
from omnix.studio.watcher import is_studio_ignored
from omnix.studio.ws_protocol import (
    msg_bootstrap_complete,
    msg_bootstrap_start,
    msg_edge_added,
    msg_error,
    msg_node_added,
    msg_pong,
    msg_stats,
)
from omnix.axiom import provider_vault
from omnix.providers.detect import identify_provider
from omnix.providers.registry import PROVIDERS

_LOG = logging.getLogger("omnix.studio")

INITIAL_STUDIO_PATH: str | None = None
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


@contextlib.asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> Any:  # noqa: ANN401, RUF029, ASYNC109
    yield
    for w in list(MANAGER.workspaces.values()):
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await w.stop()  # type: ignore[union-attr, misc, no-untyped-def]


app = FastAPI(title="OMNIX Studio", lifespan=_app_lifespan)  # type: ignore[assignment, misc, no-untyped-def]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class OpenBody(BaseModel):
    path: str


class CloseBody(BaseModel):
    workspace_id: str = Field(min_length=1)


class FileWriteBody(BaseModel):
    path: str
    content: str = ""


class FilePutBody(BaseModel):
    path: str
    content: str
    expected_last_modified: float = Field(
        description="Mtime of file when read (epoch seconds, float from OS)"
    )


class VerifyReceiptBody(BaseModel):
    receipt_path: str = Field(min_length=1)


_FINDINGS_SCAN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{20,80}$")


def _studio_project_root_path() -> Path | None:
    envp = (os.environ.get("OMNIX_STUDIO_INITIAL") or "").strip()
    raw = INITIAL_STUDIO_PATH or envp or None
    if not raw:
        return None
    try:
        return Path(raw).resolve()
    except OSError:
        return None


def _parse_host_hostname_studio(host_header: str) -> str:
    h = host_header.strip()
    if h.startswith("["):
        end = h.find("]")
        if end > 0:
            return h[: end + 1].lower()
    return h.split(":")[0].strip().lower()


def _is_localhost_request_starlette(request: Request) -> bool:
    """Match :func:`scan.handler.is_localhost_request` for ASGI (FastAPI)."""
    client = request.client
    ip = client.host if client else ""
    asgi_test = ip == "testclient"
    if not asgi_test:
        ok_ip = ip in ("127.0.0.1", "::1")
        if isinstance(ip, str) and ip.startswith("::ffff:"):
            ok_ip = ip.split(":")[-1] == "127.0.0.1"
        if not ok_ip:
            return False

    host = request.headers.get("Host", "")
    hn = _parse_host_hostname_studio(host)
    if asgi_test:
        if hn not in ("127.0.0.1", "localhost", "[::1]", "::1", "testserver"):
            return False
    elif hn not in ("127.0.0.1", "localhost", "[::1]", "::1"):
        return False

    origin = request.headers.get("Origin")
    if not origin:
        return True
    o = origin.strip()
    if o in ("null", "file://"):
        return True
    if re.match(
        r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/?$",
        o,
    ):
        return True
    return False


def _require_localhost_starlette(request: Request) -> None:
    if not _is_localhost_request_starlette(request):
        raise HTTPException(status_code=403, detail="grammar_api_localhost_only")


def _grammar_db_search_root() -> Path | None:
    if INITIAL_STUDIO_PATH:
        return Path(INITIAL_STUDIO_PATH).resolve()
    return None


def _canonical_receipt_roots() -> list[Path]:
    roots: list[Path] = [
        (Path.home() / ".omnix" / "receipts").expanduser().resolve(),
    ]
    if INITIAL_STUDIO_PATH:
        roots.append((Path(INITIAL_STUDIO_PATH) / ".omnix" / "receipts").resolve())
    return roots


def _receipt_resolves_under_allowed(abs_path: Path) -> bool:
    try:
        rp = abs_path.resolve()
    except OSError:
        return False
    for root in _canonical_receipt_roots():
        try:
            if root.is_dir():
                rp.relative_to(root)
                return True
        except ValueError:
            continue
    return False


def _omnix_cli_argv() -> list[str]:
    return [sys.executable, str(_REPO_ROOT / "omnix.py")]


def _row_to_node_public(r: sqlite3.Row) -> NodeRow:
    m = r["metadata"]
    return NodeRow(
        id=str(r["id"]),
        name=str(r["name"]),
        type=str(r["type"]),
        file_path=str(r["file_path"]) if r["file_path"] is not None else None,
        start_line=r["start_line"],
        end_line=r["end_line"],
        complexity=int(r["complexity"] or 0),
        metadata=json.loads(m) if m else None,
    )


def get_node_by_id(st: GraphStore, node_id: str) -> NodeRow | None:
    c = st.sqlite_connection()
    r = c.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if not r:
        return None
    return _row_to_node_public(r)


def _ingest_block(workspace: Workspace) -> None:
    assert isinstance(workspace, Workspace)  # noqa: S101
    evolution.begin_evolution_run()
    try:
        ingest_unified_codebase(
            str(workspace.root), workspace.store, force=False, omnix_version=__version__
        )
    finally:
        with contextlib.suppress(OSError, ValueError, RuntimeError):
            evolution.finalize_evolution_run(workspace.store.sqlite_connection())
    with contextlib.suppress(OSError, ValueError, RuntimeError):
        workspace.store.commit()


async def _start_background_ingest(w: Workspace, loop: asyncio.AbstractEventLoop) -> None:  # noqa: E501
    await loop.run_in_executor(None, _ingest_block, w)
    br = ParserBridge(loop, w)
    w.set_parser_bridge(br)  # type: ignore[union-attr, misc, no-untyped-def]
    obs = ProjectWatcher(
        str(w.root),
        br.on_filesystem,
    )
    obs.start()
    w.set_watcher(obs)  # type: ignore[union-attr, misc, no-untyped-def]
    br.start()  # type: ignore[union-attr, misc, no-untyped-def]
    w.ingest_event.set()  # type: ignore[union-attr, misc, no-untyped-def]


# --- API ---


class ProviderDetectBody(BaseModel):
    raw_key: str = Field(default="")
    custom_base_url: str | None = None


class ProviderKeyBody(BaseModel):
    raw_key: str = Field(default="")
    scope: str = Field(default="global")
    project_id: str | None = None
    override_provider: str | None = None
    custom_base_url: str | None = None
    custom_model: str | None = None


def _provider_meta_dict(meta: provider_vault.KeyMetadata) -> dict[str, Any]:
    return {
        "id": meta.id,
        "provider": meta.provider,
        "display_name": PROVIDERS.get(meta.provider).display_name
        if meta.provider in PROVIDERS
        else meta.provider,
        "scope": meta.scope,
        "fingerprint": meta.fingerprint,
        "registered_at": meta.registered_at,
        "project_id": meta.project_id,
        "custom_base_url": meta.custom_base_url,
        "custom_model": meta.custom_model,
    }


@app.post("/api/providers/detect")
async def api_provider_detect(
    request: Request, body: ProviderDetectBody
) -> dict[str, Any]:
    _require_localhost_starlette(request)
    raw = body.raw_key.strip()
    if not raw:
        raise HTTPException(status_code=422, detail="raw_key is required")
    result = await identify_provider(raw, body.custom_base_url)
    return result.to_dict()


@app.post("/api/providers/keys")
async def api_provider_keys_post(
    request: Request, body: ProviderKeyBody
) -> dict[str, Any]:
    _require_localhost_starlette(request)
    raw = body.raw_key.strip()
    if not raw:
        raise HTTPException(status_code=422, detail="raw_key is required")
    if body.scope not in ("global", "project"):
        raise HTTPException(status_code=422, detail="scope must be global or project")
    provider = body.override_provider
    if provider:
        if provider not in PROVIDERS:
            raise HTTPException(status_code=422, detail="unknown provider")
    else:
        result = await identify_provider(raw, body.custom_base_url)
        provider = result.provider
    if provider == "unknown":
        raise HTTPException(status_code=422, detail="provider could not be detected")
    if provider == "custom" and not body.custom_base_url:
        raise HTTPException(status_code=422, detail="custom_base_url is required")
    scope = "project" if body.scope == "project" else "global"
    project_id = body.project_id if scope == "project" else None
    if any(
        k.provider == provider and k.scope == scope and k.project_id == project_id
        for k in provider_vault.list_keys(project_id)
    ):
        raise HTTPException(status_code=409, detail="provider key already registered")
    try:
        meta = provider_vault.encrypt_key(
            provider,
            raw,
            scope,  # type: ignore[arg-type]
            project_id,
            custom_base_url=body.custom_base_url if provider == "custom" else None,
            custom_model=body.custom_model if provider == "custom" else None,
        )
    except Exception as e:
        _LOG.warning("provider vault encryption failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="provider vault encryption failed") from e
    return _provider_meta_dict(meta)


@app.get("/api/providers/keys")
def api_provider_keys_get(request: Request, project_id: str | None = None) -> dict[str, Any]:
    _require_localhost_starlette(request)
    return {"keys": [_provider_meta_dict(k) for k in provider_vault.list_keys(project_id)]}


@app.delete("/api/providers/keys/{key_id:path}")
def api_provider_keys_delete(request: Request, key_id: str) -> dict[str, Any]:
    _require_localhost_starlette(request)
    deleted = provider_vault.delete_key_id(key_id)
    if not deleted:
        return {"deleted": False, "reason": "not_found"}
    return {"deleted": True, "id": key_id}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/grammar/status")
def api_grammar_status(
    request: Request,
    grammar: str | None = None,
    db: str | None = None,
) -> dict[str, Any]:
    _require_localhost_starlette(request)
    root = _grammar_db_search_root()
    try:
        db_path = resolve_db_path(db, search_from=root)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        conn = open_readonly(db_path)
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=500, detail=f"cannot open database (read-only): {e}"
        ) from e
    try:
        inner = collect_grammar_status(conn, grammar)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"query failed: {e}") from e
    finally:
        conn.close()
    return {
        "db_path": str(db_path),
        "generated_at": utc_now_iso(),
        "grammars": inner["grammars"],
        "unknown_extensions": inner["unknown_extensions"],
        "llm_fallback": inner["llm_fallback"],
    }


@app.get("/api/grammar/mutations")
def api_grammar_mutations(
    request: Request,
    grammar: str | None = None,
    limit: int = 50,
    db: str | None = None,
) -> dict[str, Any]:
    _require_localhost_starlette(request)
    root = _grammar_db_search_root()
    try:
        db_path = resolve_db_path(db, search_from=root)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        conn = open_readonly(db_path)
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=500, detail=f"cannot open database (read-only): {e}"
        ) from e
    try:
        mutations = collect_mutations(conn, grammar, limit)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"query failed: {e}") from e
    finally:
        conn.close()
    return {
        "db_path": str(db_path),
        "generated_at": utc_now_iso(),
        "mutations": mutations,
    }


@app.get("/api/grammar/unknown-extensions")
def api_grammar_unknown_extensions(
    request: Request,
    limit: int = 100,
    db: str | None = None,
) -> dict[str, Any]:
    _require_localhost_starlette(request)
    root = _grammar_db_search_root()
    try:
        db_path = resolve_db_path(db, search_from=root)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        conn = open_readonly(db_path)
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=500, detail=f"cannot open database (read-only): {e}"
        ) from e
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM unknown_extensions",
        ).fetchone()
        total = int(total_row[0] or 0) if total_row else 0
        extensions = collect_unknown_extensions(conn, limit)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"query failed: {e}") from e
    finally:
        conn.close()
    return {
        "db_path": str(db_path),
        "generated_at": utc_now_iso(),
        "total": total,
        "extensions": extensions,
    }


@app.get("/api/fabric/llm-budget")
def api_fabric_llm_budget(request: Request) -> dict[str, Any]:
    _require_localhost_starlette(request)
    return {"generated_at": utc_now_iso(), **read_llm_budget_state()}


@app.post("/api/grammar/verify-receipt", response_model=None)
def api_grammar_verify_receipt(
    request: Request,
    body: VerifyReceiptBody,
) -> Any:
    _require_localhost_starlette(request)
    raw = body.receipt_path.strip()
    if not raw.startswith("/"):
        raise HTTPException(
            status_code=400,
            detail="receipt_path must be an absolute path under ~/.omnix/receipts/ "
            "or <project>/.omnix/receipts/",
        )
    receipt = Path(raw)
    try:
        resolved = receipt.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not _receipt_resolves_under_allowed(receipt):
        raise HTTPException(
            status_code=400,
            detail="receipt_path must resolve under ~/.omnix/receipts/ "
            "or the opened project's .omnix/receipts/",
        )
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="receipt not found")

    sig_path = resolved.with_suffix(".sig")
    pub = (Path.home() / ".omnix" / "keys" / "public.pem").expanduser()
    cmd = [
        *_omnix_cli_argv(),
        "axiom",
        "verify",
        str(resolved),
        str(sig_path),
        "--pubkey",
        str(pub),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={
                "receipt_path": str(resolved),
                "sig_path": str(sig_path),
                "verified": False,
                "verifier_output": "verifier timed out",
                "verified_at": utc_now_iso(),
            },
        )
    verified = result.returncode == 0
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    verifier_output = out if verified else (err or out)
    return {
        "receipt_path": str(resolved),
        "sig_path": str(sig_path),
        "verified": verified,
        "verifier_output": verifier_output,
        "verified_at": utc_now_iso(),
    }


@app.get("/api/findings/scans")
def api_findings_scans(request: Request) -> dict[str, Any]:
    _require_localhost_starlette(request)
    studio_root = _studio_project_root_path()
    if studio_root is None:
        return {"scans": []}
    project_id = compute_project_id(studio_root)
    receipts_root = (
        Path.home() / ".omnix" / "receipts" / "findings" / project_id
    ).resolve()
    if not receipts_root.is_dir():
        return {"scans": []}
    scans: list[dict[str, Any]] = []
    for sd in receipts_root.iterdir():
        if not sd.is_dir():
            continue
        mp = sd / "scan_manifest.json"
        if not mp.is_file():
            continue
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        scans.append(
            {
                "scan_id": str(m.get("scan_id") or sd.name),
                "scan_started_at": m.get("scan_started_at"),
                "scan_finished_at": m.get("scan_finished_at"),
                "finding_count": int(m.get("finding_count") or 0),
                "dir_path_relative": f"findings/{project_id}/{sd.name}",
                "manifest_kind": m.get("manifest_kind"),
            }
        )
    scans.sort(key=lambda s: str(s.get("scan_started_at") or ""), reverse=True)
    return {"scans": scans}


@app.post("/api/findings/verify-scan")
async def api_findings_verify_scan(request: Request) -> dict[str, Any]:
    _require_localhost_starlette(request)
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid JSON body") from e
    scan_id = str(body.get("scan_id") or "")
    if not _FINDINGS_SCAN_ID_RE.fullmatch(scan_id):
        raise HTTPException(
            status_code=400,
            detail="invalid scan_id format",
        )
    studio_root = _studio_project_root_path()
    if studio_root is None:
        raise HTTPException(
            status_code=400,
            detail="studio project path not configured",
        )
    project_id = compute_project_id(studio_root)
    receipts_root = (
        Path.home() / ".omnix" / "receipts" / "findings" / project_id
    ).resolve()
    try:
        cand = (receipts_root / scan_id).resolve(strict=False)
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        cand.relative_to(receipts_root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="scan_id escapes canonical receipts root",
        ) from None
    if cand.name != scan_id:
        raise HTTPException(status_code=400, detail="invalid scan path") from None
    if not cand.is_dir():
        raise HTTPException(status_code=404, detail="scan_id not found")

    ed_pub = studio_root / ".omnix" / "pubkey.pem"
    mldsa_pub = (Path.home() / ".omnix" / "keys" / "public.pem").expanduser()
    ok, reason = verify_scan_directory(cand, ed_pub, mldsa_pub)

    manifest_summary: dict[str, Any] = {}
    finding_count = 0
    mp = cand / "scan_manifest.json"
    if mp.is_file():
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            finding_count = int(m.get("finding_count") or 0)
            manifest_summary = {
                "finding_count": finding_count,
                "scan_summary": m.get("scan_summary", {}),
                "merkle_root": m.get("merkle_root"),
            }
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            manifest_summary = {}

    return {
        "verified": ok,
        "reason": reason,
        "scan_id": scan_id,
        "finding_count": finding_count,
        "manifest_summary": manifest_summary,
    }


@app.get("/favicon.ico", response_class=Response)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/ai/status")
def api_ai_status() -> dict[str, Any]:
    return {"available": False, "provider": "", "memory_stats": {}}


@app.get("/api/timeline")
def api_timeline() -> dict[str, list[Any]]:
    return {"snapshots": []}


@app.get("/api/recent")
def api_recent() -> dict[str, list[dict[str, str]]]:
    return {"recent": list_recent()}


@app.get("/api/studio/initial")
def api_studio_initial() -> dict[str, str | None]:
    envp = (os.environ.get("OMNIX_STUDIO_INITIAL") or "").strip()
    p = (INITIAL_STUDIO_PATH or envp or None)  # type: ignore[has-type, assignment, misc, no-redef, union-attr]
    return {"path": p}  # type: ignore[return-value, no-any-return]


def _parse_receipt_bound(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    s = raw.strip()
    with contextlib.suppress(ValueError):
        return float(s)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        raise HTTPException(400, "invalid receipt time bound") from None


def _receipt_source(path: Path, body: dict[str, Any]) -> str:
    stem = path.stem.lower()
    event = str(body.get("event") or body.get("kind") or "").lower()
    if stem.startswith("call_") or "fabric" in event or body.get("call_id") is not None:
        return "fabric"
    if stem.startswith("scan") or event.startswith("vault.scan"):
        return "scan"
    if stem.startswith("evolution_") or "evolution" in event:
        return "evolution"
    return "future"


def _receipt_kind(source: str, body: dict[str, Any]) -> str:
    raw = body.get("event") or body.get("kind") or body.get("type")
    if isinstance(raw, str) and raw:
        return raw
    if source == "fabric":
        return "fabric.call"
    if source == "scan":
        return "vault.scan"
    if source == "evolution":
        return "grammar.evolution"
    return "receipt"


def _receipt_target(body: dict[str, Any]) -> str:
    for key in ("target", "file", "path", "grammar", "grammar_name", "provider", "model"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    provider = body.get("provider")
    model = body.get("model")
    if provider or model:
        return " / ".join(str(x) for x in (provider, model) if x)
    return ""


_RECEIPT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,200}$")
_RECEIPT_VERIFY_CACHE: dict[str, tuple[float, float, bool]] = {}


def _load_axiom_public_key() -> bytes | None:
    """Load ~/.omnix/keys/public.pem (ML-DSA-65)."""
    try:
        from omnix.axiom import keystore  # type: ignore[import-not-found]
    except Exception:
        return None
    pub = (Path.home() / ".omnix" / "keys" / "public.pem").expanduser()
    if not pub.is_file():
        return None
    try:
        return keystore.public_from_pem(pub.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None


def _verify_receipt_detached_sig(
    *, pk: bytes | None, json_path: Path, sig_path: Path
) -> bool:
    """Verify detached signature over raw JSON bytes on disk."""
    if pk is None:
        return False
    try:
        from omnix.axiom import keystore, verify as vfy  # type: ignore[import-not-found]
    except Exception:
        return False
    try:
        raw = json_path.read_bytes()
        sig_pem = sig_path.read_text(encoding="ascii")
        sig = keystore.signature_from_pem(sig_pem)
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    try:
        return bool(vfy.verify_bytes(pk, raw, b"", sig))
    except Exception:
        return False


def _iter_receipts(
    *, since: float | None, until: float | None, limit: int
) -> list[dict[str, Any]]:
    root = (Path.home() / ".omnix" / "receipts").expanduser()
    if not root.is_dir():
        return []
    pk = _load_axiom_public_key()
    rows: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            st = path.stat()
        except OSError:
            continue
        mtime = float(st.st_mtime)
        if since is not None and mtime < since:
            continue
        if until is not None and mtime > until:
            continue
        try:
            raw = path.read_bytes()
            body0 = json.loads(raw.decode("utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            body0 = {}
            raw = b""
        body = body0 if isinstance(body0, dict) else {}
        source = _receipt_source(path, body)
        has_sig = path.with_suffix(".sig").is_file()
        verified = False
        sig_path = path.with_suffix(".sig")
        if has_sig:
            try:
                sig_mtime = float(sig_path.stat().st_mtime)
            except OSError:
                sig_mtime = 0.0
            key = str(path)
            cached = _RECEIPT_VERIFY_CACHE.get(key)
            if cached and cached[0] == float(mtime) and cached[1] == float(sig_mtime):
                verified = bool(cached[2])
            else:
                verified = _verify_receipt_detached_sig(
                    pk=pk, json_path=path, sig_path=sig_path
                )
                _RECEIPT_VERIFY_CACHE[key] = (float(mtime), float(sig_mtime), bool(verified))
        rows.append(
            {
                "receipt_id": str(path.stem),
                "kind": _receipt_kind(source, body),
                "target": _receipt_target(body),
                "hash_prefix": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
                # NOTE: "ML-DSA-65" currently indicates signature file presence only (not verified).
                "sig_alg": "ML-DSA-65" if has_sig else "unsigned",
                "has_signature": bool(has_sig),
                "verified": bool(verified) if has_sig else False,
                "mtime_iso": datetime.fromtimestamp(mtime, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "source": source,
                "path": str(path),
            }
        )
    rows.sort(key=lambda r: str(r.get("mtime_iso") or ""), reverse=True)
    return rows[:limit]


@app.get("/api/workspace/{workspace_id}/receipts")
def api_workspace_receipts(
    workspace_id: str,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    lim = max(1, min(int(limit), 500))
    return {
        "receipts": _iter_receipts(
            since=_parse_receipt_bound(since),
            until=_parse_receipt_bound(until),
            limit=lim,
        )
    }


@app.get("/api/workspace/{workspace_id}/receipts/{receipt_id}")
def api_workspace_receipt_by_id(
    workspace_id: str,
    receipt_id: str,
) -> dict[str, Any]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    rid = (receipt_id or "").strip()
    if not rid or not _RECEIPT_ID_RE.match(rid):
        raise HTTPException(400, "invalid receipt_id")
    root = (Path.home() / ".omnix" / "receipts").expanduser()
    p = (root / f"{rid}.json").resolve()
    try:
        # Prevent traversal: resolved path must stay under receipts root.
        _ = p.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(400, "invalid receipt_id") from None
    if not p.is_file():
        raise HTTPException(404, "receipt not found")
    try:
        body0 = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(500, "receipt unreadable") from None
    if not isinstance(body0, dict):
        raise HTTPException(500, "receipt payload invalid") from None
    return {"receipt": body0}


def _edge_dict(
    eid: int, sid: str, tid: str, rel: str, meta: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "id": eid,
        "source_id": sid,
        "target_id": tid,
        "relationship": rel,
        "metadata": meta or {},
    }


def _row_edge(r: sqlite3.Row) -> dict[str, Any]:  # noqa: D103
    m = r["metadata"]
    return _edge_dict(
        int(r["id"]),
        str(r["source_id"]),
        str(r["target_id"]),
        str(r["relationship"]),
        json.loads(m) if m else None,
    )


async def _run_bootstrap(websocket: WebSocket, w: Workspace) -> None:
    st = w.store
    c = st.sqlite_connection()
    t0 = time.time()
    rowf = c.execute("SELECT COUNT(*) FROM file_hashes").fetchone()  # noqa: E501
    total_files = int(rowf[0] or 0) if rowf else 0
    n_total = c.execute("SELECT COUNT(*) FROM nodes").fetchone()  # noqa: E501
    n_nodes = int(n_total[0] or 0) if n_total else 0
    e_row = c.execute("SELECT COUNT(*) FROM edges").fetchone()  # noqa: E501
    n_edges = int(e_row[0] or 0) if e_row else 0
    bmode: Any = "scratch" if w.mode == "scratch" else "existing"
    await websocket.send_text(
        json.dumps(msg_bootstrap_start(w.id, max(0, total_files), bmode))
    )
    last_s = 0.0
    for r in c.execute("SELECT * FROM nodes ORDER BY file_path, id"):
        node_r = _row_to_node_public(r)  # noqa: E501
        await websocket.send_text(
            json.dumps(msg_node_added(node_row_to_dict(node_r)))
        )  # noqa: E501
        n = time.time()
        if n - last_s >= 1.0:
            s = w.stats_dict()  # noqa: E501
            await websocket.send_text(
                json.dumps(
                    msg_stats(
                        s["files"],
                        s["functions"],
                        s["classes"],
                        s["edges"],
                        s["dark_matter"],
                        s["entangled"],
                    )
                )  # noqa: E501
            )
            last_s = n
    for r in c.execute("SELECT * FROM edges ORDER BY id"):
        await websocket.send_text(
            json.dumps(  # type: ignore[no-untyped-def, misc, no-any-return, arg-type]
                msg_edge_added(  # noqa: E501
                    _row_edge(r)  # noqa: E501
                )
            )  # noqa: E501
        )
    dur = int(1000 * (time.time() - t0))
    await websocket.send_text(
        json.dumps(msg_bootstrap_complete(dur, n_nodes, n_edges), default=str)  # noqa: E501
    )


@app.post("/api/workspace/open")
async def api_workspace_open(body: OpenBody) -> dict[str, Any]:
    try:
        w, stats0 = open_workspace(body.path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    add_recent(body.path)
    MANAGER.put(w)
    loop = asyncio.get_running_loop()  # noqa: E501
    asyncio.create_task(_start_background_ingest(w, loop))  # noqa: RUF006
    return {
        "workspace_id": w.id,
        "mode": w.mode,
        "stats": {
            "files": stats0["files"],
            "functions": stats0["functions"],
            "classes": stats0["classes"],
            "edges": stats0["edges"],
        },
    }


@app.post("/api/workspace/close")
async def api_workspace_close(body: CloseBody) -> dict[str, bool]:  # noqa: D103
    w = MANAGER.get(body.workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    await w.stop()  # type: ignore[union-attr, misc, no-untyped-def]
    MANAGER.remove(body.workspace_id)
    return {"closed": True}


async def _run_bugs_scan_task(workspace_id: str, w: Workspace, scan_id: str) -> None:
    try:
        await run_scan_for_workspace(w, scan_id)
    finally:
        MANAGER.finish_bug_scan(workspace_id, scan_id)


@app.post("/api/workspace/{workspace_id}/bugs/scan")
async def api_workspace_bugs_scan(workspace_id: str) -> JSONResponse:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    scan_id = uuid.uuid4().hex
    active_scan_id = MANAGER.try_begin_bug_scan(workspace_id, scan_id)
    if active_scan_id is not None:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Scan already in progress",
                "active_scan_id": active_scan_id,
            },
        )
    asyncio.create_task(_run_bugs_scan_task(workspace_id, w, scan_id))  # noqa: RUF006
    return JSONResponse(status_code=202, content={"scan_id": scan_id})


def _file_matches_prefix(rel: str, pfx: str) -> bool:
    if not pfx:
        return True
    return rel == pfx or rel.startswith(pfx.rstrip("/") + "/")


def _iter_listable_files(
    root: Path, pfx: str, limit: int
) -> list[dict[str, Any]]:
    root = root.resolve()
    pfx0 = pfx or ""
    out: list[dict[str, Any]] = []
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            r = f.relative_to(root).as_posix()  # noqa: E501
        except (OSError, ValueError) as e:  # noqa: F841, E501
            continue
        if is_studio_ignored(root, r) or not _file_matches_prefix(r, pfx0):
            continue
        try:  # noqa: E501
            st = f.stat()
        except OSError:
            continue
        out.append(
            {
                "path": r,
                "type": "file",
                "size": st.st_size,
                "modified": st.st_mtime,
            }
        )  # noqa: E501
        if len(out) >= limit:
            break
    return out


_TREE_SKIP_NAMES = {"__pycache__", "node_modules", ".git", ".omnix-cache"}


def _is_tree_skipped(root: Path, rel: str) -> bool:
    parts = [p for p in rel.split("/") if p]
    if any(p.startswith(".") for p in parts):
        return True
    if any(p in _TREE_SKIP_NAMES for p in parts):
        return True
    return is_studio_ignored(root, rel)


def _empty_tree_dir(name: str) -> dict[str, Any]:
    return {"name": name, "type": "dir", "children": []}


def _insert_tree_file(root_node: dict[str, Any], parts: list[str], size: int) -> None:
    cur = root_node
    for part in parts[:-1]:
        children = cur.setdefault("children", [])
        hit = next(
            (
                c
                for c in children
                if isinstance(c, dict) and c.get("name") == part and c.get("type") == "dir"
            ),
            None,
        )
        if hit is None:
            hit = _empty_tree_dir(part)
            children.append(hit)
        cur = hit
    children = cur.setdefault("children", [])
    children.append({"name": parts[-1], "type": "file", "size": int(size)})


def _sort_tree(node: dict[str, Any]) -> None:
    children = node.get("children")
    if not isinstance(children, list):
        return
    children.sort(key=lambda c: (0 if c.get("type") == "dir" else 1, str(c.get("name", ""))))
    for child in children:
        if isinstance(child, dict) and child.get("type") == "dir":
            _sort_tree(child)


def _build_file_tree(root: Path, *, max_depth: int = 6) -> dict[str, Any]:
    root = root.resolve()
    tree = _empty_tree_dir(root.name or root.as_posix())
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        parts = [p for p in rel.split("/") if p]
        if not parts or len(parts) > max_depth or _is_tree_skipped(root, rel):
            continue
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        _insert_tree_file(tree, parts, int(size))
    _sort_tree(tree)
    return tree


@app.get("/api/workspace/{workspace_id}/files")
def api_list_files(  # noqa: D103
    workspace_id: str,
    prefix: str = "",
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    lim = max(1, min(limit, 200))
    return {
        "files": _iter_listable_files(  # noqa: E501
            w.root,  # type: ignore[no-untyped-def, misc, no-any-return, arg-type, union-attr, misc]
            prefix,  # noqa: E501
            lim,  # noqa: E501
        )
    }


@app.get("/api/workspace/{workspace_id}/files/tree")
def api_files_tree(workspace_id: str) -> dict[str, dict[str, Any]]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    return {"tree": _build_file_tree(w.root)}


@app.post("/api/workspace/{workspace_id}/file")
async def api_create_file(  # noqa: D103
    workspace_id: str,
    body: FileWriteBody,
) -> dict[str, Any]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    rel = body.path.replace("\\", "/").lstrip("/")
    p = w.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)  # noqa: E501
    p.write_text(body.content, encoding="utf-8", newline="")  # noqa: E501, WPS
    return {"created": True, "path": rel}  # noqa: E501


@app.get("/api/workspace/{workspace_id}/file")
def api_get_file(  # noqa: D103
    workspace_id: str,
    path: str = Query(""),
) -> dict[str, Any]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    if not path:
        raise HTTPException(400, "path required")
    p = w.root / path
    if not p.is_file():
        raise HTTPException(404, "file not found")
    raw = p.read_text(encoding="utf-8", errors="replace")
    mtime = 0.0
    with contextlib.suppress(OSError, ValueError):
        mtime = p.stat().st_mtime
    d = detect_for_path(p)
    lang = (d.grammar_name or d.inferred_lang or "text") or "text"  # noqa: E501
    return {  # noqa: E501
        "path": path,
        "content": raw,
        "last_modified": mtime,
        "language": str(lang),  # noqa: E501
    }


def _mtime_mismatch(
    a: float, b: float, *, eps: float = 0.5e-2
) -> bool:
    return abs(float(a) - float(b)) > eps


@app.put("/api/workspace/{workspace_id}/file")
async def api_put_file(  # noqa: D103
    workspace_id: str,
    body: FilePutBody,
) -> dict[str, Any]:
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    rel = body.path.replace("\\", "/").lstrip("/")
    p = w.root / rel
    if not p.is_file():
        raise HTTPException(404, "file not found")
    try:  # noqa: E501, SIM, E501
        cur = float(p.stat().st_mtime)  # noqa: E501, WPS, E501, WPS
    except (OSError, ValueError, RuntimeError):
        cur = 0.0
    if _mtime_mismatch(float(cur), float(body.expected_last_modified)):
        raise HTTPException(409, "stale: file changed on disk")
    p.write_text(body.content, encoding="utf-8", newline="")
    nm2 = 0.0
    with contextlib.suppress(OSError, ValueError, RuntimeError, TypeError):
        nm2 = float(p.stat().st_mtime)  # noqa: E501
    return {
        "written": True,  # noqa: E501
        "new_last_modified": float(nm2),  # noqa: E501, WPS
    }


def _node_refs(
    c: sqlite3.Connection, node_id: str, *, as_target: bool
) -> list[dict[str, str | None]]:  # noqa: D103, E501
    """Callers: edges into *node*; callees: edges from *node* (CALLS only)."""
    if as_target:  # noqa: E501
        sub = (  # noqa: E501
            "SELECT source_id FROM edges WHERE target_id = ? "  # noqa: E501
            "AND relationship = 'CALLS' LIMIT 50"  # noqa: E501
        )
    else:  # noqa: E501
        sub = (  # noqa: E501
            "SELECT target_id FROM edges WHERE source_id = ? "  # noqa: E501
            "AND relationship = 'CALLS' LIMIT 50"  # noqa: E501
        )
    out: list[dict[str, str | None]] = []
    for r in c.execute(  # noqa: E501
        f"SELECT n.id, n.name, n.type FROM nodes n WHERE n.id IN ({sub})",  # noqa: S608, E501
        (node_id,),
    ):
        out.append(
            {
                "id": str(r[0]),
                "name": str(r[1]) if r[1] is not None else None,
                "type": str(r[2]) if r[2] is not None else None,
            }
        )
    return out


@app.get("/api/workspace/{workspace_id}/node/{node_id}")
def api_get_node(  # noqa: D103
    workspace_id: str,
    node_id: str,
) -> dict[str, Any]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    st = w.store
    n0 = get_node_by_id(st, node_id)  # noqa: E501
    if n0 is None:  # noqa: E501
        raise HTTPException(404, "node not found")
    c0 = st.sqlite_connection()
    return {
        "node": {
            "id": n0.id,  # noqa: E501
            "name": n0.name,
            "type": n0.type,
            "file_path": n0.file_path,
            "line_start": n0.start_line,
            "line_end": n0.end_line,
            "metadata": n0.metadata or {},
        },
        "callers": _node_refs(c0, n0.id, as_target=True),
        "callees": _node_refs(c0, n0.id, as_target=False),
        "file_path": n0.file_path,
        "line_start": n0.start_line,
        "line_end": n0.end_line,
    }


@app.get("/api/workspace/{workspace_id}/search")
def api_search(
    workspace_id: str,
    q: str = "",
    kind: str = "all",
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    query = q.strip()
    if not query:
        return {"results": []}
    if kind not in {"symbol", "file", "all"}:
        raise HTTPException(400, "kind must be symbol, file, or all")
    lim = max(1, min(int(limit), 100))
    like = f"%{query.lower()}%"
    types: tuple[str, ...]
    if kind == "file":
        types = ("file",)
    elif kind == "symbol":
        types = ("function", "method", "class")
    else:
        types = ("file", "function", "method", "class")
    ph = ",".join("?" * len(types))
    sql = (
        "SELECT name, type, file_path, start_line FROM nodes "
        f"WHERE type IN ({ph}) AND "
        "(lower(name) LIKE ? OR lower(file_path) LIKE ?) "
        "ORDER BY file_path, start_line, name LIMIT ?"
    )
    c = w.store.sqlite_connection()
    rows: list[dict[str, Any]] = []
    for row in c.execute(sql, (*types, like, like, lim)):
        typ = str(row["type"])
        rows.append(
            {
                "kind": "file" if typ == "file" else "symbol",
                "name": str(row["name"] or ""),
                "path": str(row["file_path"] or ""),
                "line": int(row["start_line"] or 0),
                "snippet": "",
            }
        )
    return {"results": rows}

async def _stats_ticker(w: Workspace, stop: asyncio.Event) -> None:
    while w._websockets:  # type: ignore[union-attr, misc, no-untyped-def]
        if stop.is_set():
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.5)
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, OSError):
            s = w.stats_dict()
            with contextlib.suppress(Exception):
                await broadcast_to_workspace(
                    w,
                    msg_stats(
                        s["files"],
                        s["functions"],
                        s["classes"],
                        s["edges"],
                        s["dark_matter"],
                        s["entangled"],
                    ),
                )
        else:
            return


@app.websocket("/ws/workspace/{workspace_id}")
async def ws_workspace(websocket: WebSocket, workspace_id: str) -> None:
    w = MANAGER.get(workspace_id)
    if w is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    w.add_ws(websocket)  # type: ignore[union-attr, misc, no-untyped-def]
    stop = asyncio.Event()
    t_stats = asyncio.create_task(_stats_ticker(w, stop), name="studio-stats")
    try:
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        except asyncio.TimeoutError:
            return
        try:
            d0 = json.loads(first) if first else {}
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps(msg_error("invalid JSON", True)))
            return
        if d0.get("type") != "subscribe" or d0.get("workspace_id") != workspace_id:
            await websocket.send_text(
                json.dumps(
                    msg_error("expected subscribe with matching workspace_id", True)
                )
            )
            return
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(w.ingest_event.wait(), timeout=600.0)  # type: ignore[union-attr, misc, no-untyped-def]
        await _run_bootstrap(websocket, w)
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except (asyncio.TimeoutError,):
                continue
            try:
                d2 = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if d2.get("type") == "ping":
                await websocket.send_text(
                    json.dumps(msg_pong(float(d2.get("ts", 0.0))))
                )
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        stop.set()
        t_stats.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t_stats
        w.remove_ws(websocket)  # type: ignore[union-attr, misc, no-untyped-def]


if (_FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="studio-assets",
    )


@app.get("/", response_model=None)  # noqa: E501
def spa_index() -> FileResponse | JSONResponse:  # noqa: D103
    idx = _FRONTEND_DIST / "index.html"
    if idx.is_file():
        return FileResponse(str(idx))
    return JSONResponse(
        {"detail": "Build frontend: cd src/omnix/studio/frontend && npm run build"},
        status_code=200,
    )


def run(
    *,
    project_path: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
) -> None:  # noqa: D103
    import uvicorn  # noqa: WPS433

    global INITIAL_STUDIO_PATH  # noqa: PLW0603
    p = int((os.environ.get("OMNIX_STUDIO_PORT") or "7778").strip() or 7778)
    if port is not None:
        p = int(port)
    if project_path is not None:
        INITIAL_STUDIO_PATH = str(Path(project_path).resolve())
    else:
        INITIAL_STUDIO_PATH = None
    uvicorn.run(app, host=host, port=p)
