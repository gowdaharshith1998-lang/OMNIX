"""Object-storage abstraction.

Default backend is Cloudflare R2 (S3-compatible, $0.015/GB, zero egress).
For AWS-residency or BYOK customers, the s3 backend talks to AWS with optional
SSE-KMS using the tenant's CMK ARN.

For tests, an in-memory backend ships in this module. moto provides full S3
mocking for the s3 backend.

API contract:
  StorageBackend.put_object(key, data, sha256=None) -> StoredObject
  StorageBackend.get_object(key) -> bytes
  StorageBackend.delete_object(key) -> None
  StorageBackend.head_object(key) -> StoredObject
  StorageBackend.iter_keys(prefix) -> Iterator[str]
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from omnix.cloud.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str
    backend: str
    etag: str | None = None


class StorageError(RuntimeError):
    pass


class StorageBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def put_object(
        self, key: str, data: bytes | io.IOBase, sha256: str | None = None
    ) -> StoredObject:
        ...

    @abstractmethod
    def get_object(self, key: str) -> bytes:
        ...

    @abstractmethod
    def delete_object(self, key: str) -> None:
        ...

    @abstractmethod
    def head_object(self, key: str) -> StoredObject:
        ...

    @abstractmethod
    def iter_keys(self, prefix: str = "") -> Iterator[str]:
        ...


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_all(src: bytes | io.IOBase) -> bytes:
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    if isinstance(src, io.IOBase):
        return src.read()
    raise TypeError(f"unsupported stream type: {type(src)!r}")


class MemoryStorage(StorageBackend):
    """In-process backend used for tests."""

    name = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, bytes] = {}

    def put_object(
        self, key: str, data: bytes | io.IOBase, sha256: str | None = None
    ) -> StoredObject:
        payload = _read_all(data)
        digest = _sha256_of(payload)
        if sha256 and sha256 != digest:
            raise StorageError(
                f"sha256 mismatch on {key}: expected {sha256}, got {digest}"
            )
        with self._lock:
            self._store[key] = payload
        return StoredObject(key=key, size=len(payload), sha256=digest, backend=self.name)

    def get_object(self, key: str) -> bytes:
        with self._lock:
            if key not in self._store:
                raise StorageError(f"no such key: {key}")
            return self._store[key]

    def delete_object(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def head_object(self, key: str) -> StoredObject:
        with self._lock:
            if key not in self._store:
                raise StorageError(f"no such key: {key}")
            payload = self._store[key]
        return StoredObject(
            key=key, size=len(payload), sha256=_sha256_of(payload), backend=self.name
        )

    def iter_keys(self, prefix: str = "") -> Iterator[str]:
        with self._lock:
            keys = sorted(self._store)
        for k in keys:
            if k.startswith(prefix):
                yield k


class _S3LikeStorage(StorageBackend):
    """Shared logic between R2 (S3-compatible) and S3."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str | None,
        secret_key: str | None,
        sse_kms_key_arn: str | None = None,
    ) -> None:
        import boto3  # imported lazily to keep tests cheap

        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        self.sse_kms_key_arn = sse_kms_key_arn
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put_object(
        self, key: str, data: bytes | io.IOBase, sha256: str | None = None
    ) -> StoredObject:
        payload = _read_all(data)
        digest = _sha256_of(payload)
        if sha256 and sha256 != digest:
            raise StorageError(
                f"sha256 mismatch on {key}: expected {sha256}, got {digest}"
            )
        extra: dict = {"Metadata": {"sha256": digest}}
        if self.sse_kms_key_arn:
            extra["ServerSideEncryption"] = "aws:kms"
            extra["SSEKMSKeyId"] = self.sse_kms_key_arn
        resp = self._client.put_object(
            Bucket=self.bucket, Key=key, Body=payload, **extra
        )
        return StoredObject(
            key=key,
            size=len(payload),
            sha256=digest,
            backend=self.name,
            etag=resp.get("ETag", "").strip('"') or None,
        )

    def get_object(self, key: str) -> bytes:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # botocore.ClientError lacks a clean isinstance hook
            raise StorageError(f"get_object({key}): {exc}") from exc
        return obj["Body"].read()

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def head_object(self, key: str) -> StoredObject:
        try:
            obj = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"head_object({key}): {exc}") from exc
        size = int(obj.get("ContentLength", 0))
        digest = obj.get("Metadata", {}).get("sha256", "")
        return StoredObject(
            key=key, size=size, sha256=digest, backend=self.name, etag=obj.get("ETag")
        )

    def iter_keys(self, prefix: str = "") -> Iterator[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                yield obj["Key"]


class R2Storage(_S3LikeStorage):
    name = "r2"

    def __init__(self, bucket: str, *, account_id: str | None = None, **kw) -> None:
        endpoint = (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else kw.pop("endpoint_url", None)
        )
        super().__init__(
            bucket=bucket,
            endpoint_url=endpoint,
            region=kw.pop("region", "auto"),
            access_key=kw.pop("access_key", os.environ.get("R2_ACCESS_KEY_ID")),
            secret_key=kw.pop("secret_key", os.environ.get("R2_SECRET_ACCESS_KEY")),
        )


class S3Storage(_S3LikeStorage):
    name = "s3"

    def __init__(self, bucket: str, *, region: str = "us-east-1", **kw) -> None:
        super().__init__(
            bucket=bucket,
            endpoint_url=kw.pop("endpoint_url", None),
            region=region,
            access_key=kw.pop("access_key", os.environ.get("AWS_ACCESS_KEY_ID")),
            secret_key=kw.pop("secret_key", os.environ.get("AWS_SECRET_ACCESS_KEY")),
            sse_kms_key_arn=kw.pop("sse_kms_key_arn", None),
        )


_BACKEND_SINGLETON: StorageBackend | None = None
_BACKEND_LOCK = threading.Lock()


def get_storage(*, override: StorageBackend | None = None) -> StorageBackend:
    """Resolve the configured storage backend (process-wide singleton).

    Tests can pass ``override`` to inject a MemoryStorage or moto-S3 backend.
    """
    global _BACKEND_SINGLETON
    if override is not None:
        with _BACKEND_LOCK:
            _BACKEND_SINGLETON = override
        return override

    with _BACKEND_LOCK:
        if _BACKEND_SINGLETON is not None:
            return _BACKEND_SINGLETON
        settings = get_settings()
        if settings.storage_backend == "memory":
            _BACKEND_SINGLETON = MemoryStorage()
        elif settings.storage_backend == "r2":
            _BACKEND_SINGLETON = R2Storage(
                settings.storage_bucket, account_id=settings.storage_endpoint
            )
        elif settings.storage_backend == "s3":
            _BACKEND_SINGLETON = S3Storage(
                settings.storage_bucket,
                region=settings.storage_region,
                endpoint_url=settings.storage_endpoint,
            )
        else:
            raise StorageError(f"unknown storage backend: {settings.storage_backend}")
        return _BACKEND_SINGLETON


def reset_storage_singleton() -> None:
    """Test hook — wipe the singleton."""
    global _BACKEND_SINGLETON
    with _BACKEND_LOCK:
        _BACKEND_SINGLETON = None
