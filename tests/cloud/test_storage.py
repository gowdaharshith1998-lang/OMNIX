"""Tests for the storage abstraction (memory backend + sha256 contract)."""

from __future__ import annotations

import hashlib
import io

import pytest

from omnix.cloud.ingest.storage import (
    MemoryStorage,
    StorageError,
    get_storage,
    reset_storage_singleton,
)


@pytest.fixture(autouse=True)
def _reset_storage():
    reset_storage_singleton()
    yield
    reset_storage_singleton()


def test_memory_backend_roundtrip():
    backend = MemoryStorage()
    obj = backend.put_object("foo/bar.bin", b"hello")
    assert obj.size == 5
    assert obj.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert backend.get_object("foo/bar.bin") == b"hello"


def test_memory_backend_iter_keys_prefix():
    backend = MemoryStorage()
    backend.put_object("a/1.bin", b"x")
    backend.put_object("a/2.bin", b"y")
    backend.put_object("b/1.bin", b"z")

    a_keys = list(backend.iter_keys("a/"))
    assert a_keys == ["a/1.bin", "a/2.bin"]


def test_memory_backend_supports_iobase():
    backend = MemoryStorage()
    stream = io.BytesIO(b"streamed-bytes")
    obj = backend.put_object("k", stream)
    assert obj.size == len(b"streamed-bytes")


def test_memory_backend_rejects_sha_mismatch():
    backend = MemoryStorage()
    with pytest.raises(StorageError):
        backend.put_object("k", b"hello", sha256="0" * 64)


def test_get_storage_resolves_memory_from_settings():
    backend = get_storage()
    assert isinstance(backend, MemoryStorage)


def test_get_storage_override_swaps_singleton():
    a = MemoryStorage()
    b = MemoryStorage()
    get_storage(override=a)
    assert get_storage() is a
    get_storage(override=b)
    assert get_storage() is b
