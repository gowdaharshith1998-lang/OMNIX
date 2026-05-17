# Compliance: P11 — avoid echoing key material in CI output.

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from omnix.scan import handler as h
from omnix.scan import patterns, receipts, scanner, store


class _Hdr:
    def __init__(self, host: str, origin: str | None) -> None:
        self._d: dict[str, str] = {"Host": host}
        if origin is not None:
            self._d["Origin"] = origin

    def get(self, k: str, default: str | None = None) -> str | None:
        return self._d.get(k, default)


def _fh(
    client_ip: str, host: str, origin: str | None, body_out: bytes | None = None
) -> Any:
    class P:
        client_address: tuple
        headers: _Hdr
        wfile: BytesIO
        rfile: BytesIO
        _omit_response_body: bool = False

    f = P()  # type: ignore[assignment, misc] — duck handler
    f.client_address = (client_ip, 9)
    f.headers = _Hdr(host, origin)
    f.wfile = BytesIO()
    f.rfile = BytesIO(b"{}")
    return f


@pytest.fixture
def clear_store() -> Any:
    store.set_detection_store_for_tests(
        store.DetectionStore(time_fn=time.monotonic, on_expire=None)
    )
    yield
    store.set_detection_store_for_tests(None)


def test_is_localhost_ok() -> None:
    f = _fh("127.0.0.1", "127.0.0.1:7777", "http://127.0.0.1:7777")
    assert h.is_localhost_request(f) is True  # type: ignore[arg-type]


def test_is_localhost_rejects_remote_ip() -> None:
    f = _fh("8.8.8.8", "127.0.0.1:7777", "http://127.0.0.1:7777")
    assert h.is_localhost_request(f) is False  # type: ignore[arg-type]


def test_is_localhost_rejects_bad_host() -> None:
    f = _fh("127.0.0.1", "evil.com", None)
    assert h.is_localhost_request(f) is False  # type: ignore[arg-type]


def test_is_localhost_rejects_bad_origin() -> None:
    f = _fh("127.0.0.1", "127.0.0.1:1", "http://evil.com")
    assert h.is_localhost_request(f) is False  # type: ignore[arg-type]


def test_is_localhost_accepts_localhost_origin() -> None:
    f = _fh("127.0.0.1", "localhost:9999", "http://localhost:9999")
    assert h.is_localhost_request(f) is True  # type: ignore[arg-type]


def test_is_localhost_accepts_no_origin() -> None:
    f = _fh("127.0.0.1", "127.0.0.1:77", None)
    assert h.is_localhost_request(f) is True  # type: ignore[arg-type]


def test_is_localhost_accepts_string_null_origin() -> None:
    f = _fh("127.0.0.1", "127.0.0.1:1", "null")
    assert h.is_localhost_request(f) is True  # type: ignore[arg-type]


def test_is_localhost_ipv6() -> None:
    f = _fh("::1", "[::1]:8080", None)
    assert h.is_localhost_request(f) is True  # type: ignore[arg-type]


def test_is_localhost_mapped_ipv4() -> None:
    f = _fh("::ffff:127.0.0.1", "127.0.0.1:1", "http://127.0.0.1:1")
    assert h.is_localhost_request(f) is True  # type: ignore[arg-type]


def test_scan_finds_env_var_anthropic(
    clear_store: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = "sk-ant-api03-" + "a" * 32
    monkeypatch.setenv("OMNIX_TEST_XKEY", key)
    c, _, _ = scanner.run_scan(tmp_path, home=tmp_path)
    found = [x for x in c if x.get("source") == "env:OMNIX_TEST_XKEY"]
    assert len(found) == 1
    assert found[0]["provider"] == "anthropic"


def test_scan_finds_openai(
    clear_store: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = "sk-" + "b" * 30
    monkeypatch.setenv("K", key)
    c, _, _ = scanner.run_scan(tmp_path, home=tmp_path)
    assert any(
        x["provider"] == "openai" and x["source"] == "env:K" for x in c
    )


def test_scan_finds_google(
    clear_store: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = "AIza" + "c" * 32
    monkeypatch.setenv("G", key)
    c, _, _ = scanner.run_scan(tmp_path, home=tmp_path)
    assert any(x["provider"] == "google" and x["source"] == "env:G" for x in c)


def test_scan_masks_preview() -> None:
    k = "sk-ant-api03-" + "a" * 32
    m = patterns.masked_preview("anthropic", k)
    assert k[-4:] in m
    assert "****" in m
    assert k not in m


def test_scan_rejects_oversized_file(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path
    odir = home / ".config" / "openai"
    odir.mkdir(parents=True)
    p = odir / "config_big.json"
    p.write_bytes(b"X")
    with p.open("r+b") as f2:
        f2.seek(2 * 1024 * 1024)
        f2.write(b"0")
    c, _, _ = scanner.run_scan(tmp_path, home=home)
    assert not any("config_big" in (x.get("source") or "") for x in c)


def test_scan_rejects_path_traversal_symlink(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path
    odir = home / ".config" / "openai"
    odir.mkdir(parents=True)
    etcp = tmp_path / "sec"
    etcp.write_text("K=" + "sk-" + "x" * 30, encoding="utf-8")
    link = odir / "config.json"
    try:
        link.symlink_to(etcp)
    except OSError:
        pytest.skip("symlinks not allowed")
    c, _, _ = scanner.run_scan(tmp_path, home=home)
    for x in c:
        assert str(etcp.resolve()) not in (x.get("source") or "")


def test_scan_skips_git_tracked_dotenv(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".env").write_text("K=" + "sk-" + "y" * 30 + "\n", encoding="utf-8")
    m = mock.patch.object(scanner, "is_dotenv_git_tracked", return_value=True)
    with m:
        c, _, reasons = scanner.run_scan(repo, home=tmp_path)
    assert "skipped" in " ".join(reasons)
    assert not any("file:./.env" in (x.get("source") or "") for x in c)


def test_scan_ollama_probe_offline(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    def boom(*_a: object, **_k: object) -> object:
        raise urllib.error.URLError("nope")  # noqa: S106

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    c, s, _ = scanner.run_scan(tmp_path, home=tmp_path)
    assert "probe:ollama-localhost(offline)" in s
    assert not any(x["provider"] == "ollama" for x in c)


def test_scan_ollama_probe_when_running(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with mock.patch.object(urllib.request, "urlopen", _fake_urlopen_200):
        c, s, _ = scanner.run_scan(tmp_path, home=tmp_path)
    assert "probe:ollama-localhost" in s
    assert any(
        x["provider"] == "ollama" and x["source"] == "probe:ollama-localhost" for x in c
    )


def _fake_urlopen_200(*_a: object, **_k: object) -> object:
    class Ctx:
        def getcode(self) -> int:
            return 200

        def __enter__(self) -> Ctx:
            return self

        def __exit__(self, *a: object) -> None:
            return

    return Ctx()


def test_consume_flow(clear_store: object) -> None:
    st = store.get_detection_store()
    did = st.add_detection("openai", "sk-" + "z" * 30, 35, "env:T")
    got = st.pop_detection(did)
    assert got and got["provider"] == "openai" and "key" in got
    assert st.pop_detection(did) is None


def test_consume_expired_mock_time(clear_store: object) -> None:
    t0 = {"n": 0.0}
    s2 = store.DetectionStore(
        time_fn=lambda: t0["n"],
        on_expire=None,
    )
    store.set_detection_store_for_tests(s2)
    did = s2.add_detection("openai", "a", 1, "e")
    t0["n"] = 500.0
    assert s2.pop_detection(did) is None
    store.set_detection_store_for_tests(
        store.DetectionStore(time_fn=time.monotonic, on_expire=None)
    )


def test_consume_unknown(clear_store: object) -> None:
    st = store.get_detection_store()
    assert st.pop_detection("deadbeefdeadbeefdeadbeefdeadbeef") is None


def test_receipt_event_only_contains_safe_fields(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rdir = tmp_path / "receipts"
    rdir.mkdir(parents=True)
    monkeypatch.setattr(
        receipts,
        "_SK_PATH",
        tmp_path / "nope",
    )
    monkeypatch.setattr(
        receipts,
        "_RECEIPT_DIR",
        rdir,
    )
    p = receipts.write_vault_scan_receipt(
        sources_scanned=["a", "b"],
        detections_found=0,
        host="h",
    )
    assert p
    j = next(rdir.glob("scan_*.json"))
    raw = j.read_text(encoding="utf-8")
    assert "sk-" not in raw
    assert "AIza" not in raw


def test_post_scan_403() -> None:
    fh = _fh("1.1.1.1", "127.0.0.1:1", "http://127.0.0.1:1")
    with mock.patch.object(h, "_send_json") as m:
        h.handle_vault_scan_post(
            fh,  # type: ignore[arg-type]
            project_root=Path("."),
        )
    cargs = m.call_args[0]
    assert cargs[1] == 403


def test_end_to_end_scan_happy(
    clear_store: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pr = tmp_path
    k = "sk-" + "q" * 30
    monkeypatch.setenv("E2E_X", k)
    fh = _fh("127.0.0.1", "127.0.0.1:1", None)
    with mock.patch.object(h, "_send_json") as sj:
        h.handle_vault_scan_post(
            fh,  # type: ignore[arg-type]
            project_root=pr,
        )
    assert sj.call_args[0][1] == 200
    dets = sj.call_args[0][2]["detections"]
    assert len(dets) >= 1
    st = store.get_detection_store()
    one = dets[0]["detection_id"]
    p = st.pop_detection(one)
    assert p and "key" in p
