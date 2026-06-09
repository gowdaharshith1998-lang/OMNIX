"""Encrypted provider key vault for Provider Fabric BYOK."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from omnix.receipts.finding_keys import ensure_project_key, omnix_home, project_privkey_path
from omnix.receipts.finding_receipt import compute_project_id

Scope = Literal["global", "project"]

_SALT = b"omnix-provider-vault-v1"
_INFO = b"omnix-providers-aes-gcm-key"
_SERVICE = "omnix-providers"


@dataclass(frozen=True)
class KeyMetadata:
    id: str
    provider: str
    scope: Scope
    fingerprint: str
    registered_at: str
    project_id: str | None = None
    custom_base_url: str | None = None
    custom_model: str | None = None


@dataclass(frozen=True)
class KeyLookup:
    key: str
    metadata: KeyMetadata


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _providers_dir() -> Path:
    return omnix_home() / ".omnix" / "providers"


def _index_path() -> Path:
    return _providers_dir() / "index.json"


def _key_id(provider: str, scope: Scope, project_id: str | None) -> str:
    pid = project_id if scope == "project" else "global"
    return f"{scope}:{provider}:{pid}"


def _username(provider: str, scope: Scope, project_id: str | None) -> str:
    return _key_id(provider, scope, project_id)


def _enc_path(provider: str, scope: Scope, project_id: str | None) -> Path:
    suffix = f"-{project_id}" if scope == "project" and project_id else ""
    safe = provider.replace("/", "_").replace(":", "_")
    return _providers_dir() / scope / f"{safe}{suffix}.enc"


def _load_index() -> dict[str, KeyMetadata]:
    p = _index_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, KeyMetadata] = {}
    for item in raw.get("keys", []) if isinstance(raw, dict) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out[item["id"]] = KeyMetadata(**item)
    return out


def _save_index(index: dict[str, KeyMetadata]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(p.parent, 0o700)
    data = {"keys": [asdict(v) for v in sorted(index.values(), key=lambda k: k.id)]}
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(p, 0o600)


def _project_id_from_cwd() -> str:
    root = Path.cwd().resolve()
    ensure_project_key(root)
    return compute_project_id(root)


def _private_key_path(project_id: str | None) -> Path:
    pid = project_id or _project_id_from_cwd()
    path = project_privkey_path(pid)
    if not path.is_file() and project_id is None:
        ensure_project_key(Path.cwd().resolve())
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        priv = Ed25519PrivateKey.generate()
        path.write_bytes(
            priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        os.chmod(path, 0o600)
    return path


def _derive_aes_key(project_id: str | None) -> bytes:
    pem = _private_key_path(project_id).read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("provider vault requires Ed25519 project key")
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=_INFO,
    ).derive(raw)


def _seal(raw_key: str, metadata: KeyMetadata) -> str:
    nonce = os.urandom(12)
    aes = AESGCM(_derive_aes_key(metadata.project_id))
    aad = metadata.id.encode("utf-8")
    ct = aes.encrypt(nonce, raw_key.encode("utf-8"), aad)
    blob = {
        "v": 1,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ct).decode("ascii"),
        "metadata": asdict(metadata),
    }
    return json.dumps(blob, sort_keys=True)


def _open(blob: str, project_id: str | None) -> str:
    data = json.loads(blob)
    meta = KeyMetadata(**data["metadata"])
    aes = AESGCM(_derive_aes_key(project_id or meta.project_id))
    nonce = base64.b64decode(data["nonce"])
    ct = base64.b64decode(data["ciphertext"])
    raw = aes.decrypt(nonce, ct, meta.id.encode("utf-8"))
    return raw.decode("utf-8")


def _keyring_module() -> Any | None:
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    return keyring


def _write_keyring(username: str, blob: str) -> bool:
    kr = _keyring_module()
    if kr is None:
        return False
    try:
        kr.set_password(_SERVICE, username, blob)
        return True
    except Exception:
        return False


def _read_keyring(username: str) -> str | None:
    kr = _keyring_module()
    if kr is None:
        return None
    try:
        val = kr.get_password(_SERVICE, username)
    except Exception:
        return None
    return val if isinstance(val, str) and val else None


def _delete_keyring(username: str) -> None:
    kr = _keyring_module()
    if kr is None:
        return
    try:
        kr.delete_password(_SERVICE, username)
    except Exception:
        return


def _write_file(path: Path, blob: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_text(blob, encoding="utf-8")
    os.chmod(path, 0o600)


def encrypt_key(
    provider_name: str,
    raw_key: str,
    scope: Scope,
    project_id: str | None = None,
    *,
    custom_base_url: str | None = None,
    custom_model: str | None = None,
) -> KeyMetadata:
    if scope not in ("global", "project"):
        raise ValueError("scope must be global or project")
    pid = (project_id or _project_id_from_cwd()) if scope == "project" else None
    meta = KeyMetadata(
        id=_key_id(provider_name, scope, pid),
        provider=provider_name,
        scope=scope,
        fingerprint=raw_key[-4:] if raw_key else "",
        registered_at=_now(),
        project_id=pid,
        custom_base_url=custom_base_url,
        custom_model=custom_model,
    )
    blob = _seal(raw_key, meta)
    username = _username(provider_name, scope, pid)
    if not _write_keyring(username, blob):
        _write_file(_enc_path(provider_name, scope, pid), blob)
    index = _load_index()
    index[meta.id] = meta
    _save_index(index)
    return meta


def decrypt_key(provider_name: str, scope: Scope, project_id: str | None = None) -> str:
    pid = (project_id or _project_id_from_cwd()) if scope == "project" else None
    username = _username(provider_name, scope, pid)
    blob = _read_keyring(username)
    path = _enc_path(provider_name, scope, pid)
    if blob is None and path.is_file():
        blob = path.read_text(encoding="utf-8")
    if blob is None:
        raise FileNotFoundError("provider key not found")
    return _open(blob, pid)


def get_key(provider_name: str, project_id: str | None = None) -> KeyLookup | None:
    index = _load_index()
    scopes: tuple[tuple[Scope, str | None], ...] = (
        (("project", project_id), ("global", None))
        if project_id
        else (("global", None),)
    )
    for scope, pid in scopes:
        kid = _key_id(provider_name, scope, pid)
        meta = index.get(kid)
        if meta is None:
            continue
        try:
            raw = decrypt_key(provider_name, scope, pid)
        except FileNotFoundError:
            continue
        return KeyLookup(key=raw, metadata=meta)
    return None


def list_keys(project_id: str | None = None) -> list[KeyMetadata]:
    vals = list(_load_index().values())
    if project_id is not None:
        vals = [m for m in vals if m.scope == "global" or m.project_id == project_id]
    return sorted(vals, key=lambda m: (m.provider, m.scope, m.project_id or ""))


def delete_key(
    provider_name: str,
    scope: Scope,
    project_id: str | None = None,
) -> bool:
    pid = (project_id or _project_id_from_cwd()) if scope == "project" else None
    username = _username(provider_name, scope, pid)
    existed = False
    if _read_keyring(username) is not None:
        existed = True
    _delete_keyring(username)
    path = _enc_path(provider_name, scope, pid)
    if path.exists():
        existed = True
        path.unlink()
    index = _load_index()
    kid = _key_id(provider_name, scope, pid)
    if kid in index:
        existed = True
        index.pop(kid, None)
        _save_index(index)
    return existed


def delete_key_id(key_id: str) -> bool:
    meta = _load_index().get(key_id)
    if meta is None:
        return False
    return delete_key(meta.provider, meta.scope, meta.project_id)
