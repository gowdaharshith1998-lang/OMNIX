# Compliance: P11 — tests avoid echoing key material.

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from click.testing import CliRunner

from omnix.cli import main
from omnix.fabric import budget, dispatcher, health, receipts, telemetry
from omnix.fabric import config as fc
from omnix.fabric import dedup as dedup_mod
from omnix.fabric.handler import (
    handle_fabric_dispatch_post,
    handle_fabric_spend_get,
    handle_fabric_status_get,
    handle_fabric_telemetry_get,
    reset_executor_for_tests,
)
from tests.fabric import mocks


class _Hdr:
    def __init__(self, host: str, origin: str | None) -> None:
        self._d: dict[str, str] = {"Host": host}
        if origin is not None:
            self._d["Origin"] = origin

    def get(self, k: str, default: str | None = None) -> str | None:
        return self._d.get(k, default)


def _fh(
    client_ip: str, host: str, origin: str | None
) -> Any:
    class P:
        client_address: tuple
        headers: _Hdr
        wfile: BytesIO
        _omit_response_body: bool = False

    f = P()  # type: ignore[assignment, misc]
    f.client_address = (client_ip, 9)
    f.headers = _Hdr(host, origin)
    f.wfile = BytesIO()
    return f


@pytest.fixture(autouse=True)
def fabric_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    cfgp = tmp_path / "fabric_config.json"
    fc.save_config(fc.default_config(), cfgp)
    monkeypatch.setattr(fc, "CONFIG_PATH", cfgp)
    rdir = tmp_path / "receipts"
    rdir.mkdir(parents=True, exist_ok=True)
    receipts.set_paths_for_tests(receipt_dir=rdir, secret_path=tmp_path / "none.pem")
    budget.set_time_fn_for_tests(None)
    health.set_time_fn_for_tests(None)
    dispatcher.reset_runtime_for_tests()
    reset_executor_for_tests()
    dedup_mod.reset_for_tests()
    telemetry.reset_for_tests()
    yield
    reset_executor_for_tests()
    receipts.reset_paths_for_tests()


def _base_payload(**kwargs: Any) -> dict[str, Any]:
    p = {
        "agent_id": "agent1",
        "task_kind": "debug",
        "messages": [{"role": "user", "content": "Say hello"}],
        "options": {"max_tokens": 50, "timeout_ms": 5000},
        "provider_key": {"provider": "anthropic", "key": "k"},
    }
    p.update(kwargs)
    return p


def test_dispatch_rejects_non_localhost() -> None:
    h = _fh("127.0.0.1", "evil.com", "http://evil.com")
    with mock.patch("omnix.fabric.handler._send_json") as sj:
        handle_fabric_dispatch_post(h, _base_payload())  # type: ignore[arg-type]
    assert sj.call_args[0][1] == 403
    assert "dispatch_localhost_only" in str(sj.call_args[0][2])


def test_dispatch_rejects_bad_provider_key_shape() -> None:
    with pytest.raises(ValueError):
        dispatcher.dispatch({"agent_id": "a", "messages": []})
    with pytest.raises(ValueError):
        dispatcher.dispatch(
            {
                "agent_id": "a",
                "messages": [],
                "provider_key": {"provider": "nope", "key": "x"},
            }
        )


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_anthropic_happy_path(m_url: Any) -> None:
    m_url.return_value = mocks.anthropic_ok("yo", 10, 5)
    out = dispatcher.dispatch(_base_payload())
    assert out["ok"] is True
    assert out["content"] == "yo"
    assert out["usage"]["tokens_in"] == 10
    m_url.assert_called()


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_openai_happy_path(m_url: Any) -> None:
    m_url.return_value = mocks.openai_ok("hi", 8, 4)
    p = _base_payload()
    p["provider_key"] = {"provider": "openai", "key": "sk"}
    p["options"] = {**p["options"], "provider_override": "openai"}
    out = dispatcher.dispatch(p)
    assert out["ok"] is True
    assert out["content"] == "hi"


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_google_happy_path(m_url: Any) -> None:
    m_url.return_value = mocks.google_ok("g", 3, 2)
    p = _base_payload()
    p["provider_key"] = {"provider": "google", "key": "gk"}
    p["options"] = {**p["options"], "provider_override": "google"}
    out = dispatcher.dispatch(p)
    assert out["ok"] is True
    assert out["content"] == "g"


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_ollama_happy_path(m_url: Any) -> None:
    m_url.return_value = mocks.ollama_ok("local", 2, 1)
    p = _base_payload()
    p["provider_key"] = {"provider": "ollama", "key": ""}
    p["options"] = {**p["options"], "provider_override": "ollama"}
    out = dispatcher.dispatch(p)
    assert out["ok"] is True


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_retry_on_429(m_url: Any) -> None:
    ok = mocks.anthropic_ok("win", 1, 1)

    def side_effect(*a: Any, **kw: Any) -> Any:
        if not hasattr(side_effect, "n"):
            side_effect.n = 0  # type: ignore[attr-defined]
        side_effect.n += 1  # type: ignore[attr-defined]
        if side_effect.n < 3:
            raise mocks.http_error(429, "{}")
        return ok

    m_url.side_effect = side_effect
    out = dispatcher.dispatch(_base_payload())
    assert out["ok"] is True
    assert out["content"] == "win"
    assert m_url.call_count == 3


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_retry_on_529(m_url: Any) -> None:
    ok = mocks.anthropic_ok("ok", 1, 1)
    m_url.side_effect = [mocks.http_error(529, "{}"), ok]
    out = dispatcher.dispatch(_base_payload())
    assert out["ok"] is True


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_retry_on_5xx(m_url: Any) -> None:
    ok = mocks.anthropic_ok("ok", 1, 1)
    m_url.side_effect = [mocks.http_error(503, "{}"), ok]
    out = dispatcher.dispatch(_base_payload())
    assert out["ok"] is True


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_failover_chain(m_url: Any) -> None:
    calls = {"n": 0}

    def side_effect(req: Any, timeout: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise mocks.http_error(401, "{}")
        return mocks.openai_ok("from-openai", 2, 2)

    m_url.side_effect = side_effect
    p = _base_payload()
    p["provider_keys"] = {"anthropic": "ak", "openai": "ok"}
    p["provider_key"] = {"provider": "anthropic", "key": "ak"}
    out = dispatcher.dispatch(p)
    assert out["ok"] is True
    assert out["content"] == "from-openai"
    assert out["provider"] == "openai"


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_dispatch_exhausted_retries(m_url: Any) -> None:
    m_url.side_effect = mocks.http_error(429, "{}")
    p = _base_payload()
    p["options"] = {**p["options"], "provider_override": "anthropic"}
    out = dispatcher.dispatch(p)
    assert out["ok"] is False
    assert out["error"] == "exhausted_retries"


def test_dispatch_deduplicates_on_idempotency_key() -> None:
    started = threading.Event()

    def fake_urlopen(*a: Any, **kw: Any) -> Any:
        started.set()
        time.sleep(0.12)
        return mocks.anthropic_ok("once", 1, 1)

    p = _base_payload()
    p["options"] = {**p["options"], "idempotency_key": "idem-1"}

    with mock.patch("omnix.fabric.providers.common.urllib.request.urlopen", fake_urlopen):
        ex = ThreadPoolExecutor(max_workers=2)
        f1 = ex.submit(dispatcher.dispatch, p)
        assert started.wait(timeout=5)
        f2 = ex.submit(dispatcher.dispatch, p)
        results = [f1.result(timeout=30), f2.result(timeout=30)]
        ex.shutdown(wait=False)

    assert results[0]["ok"] and results[1]["ok"]
    assert results[0]["call_id"] == results[1]["call_id"]
    assert results[1].get("deduped") is True
    deduped_rows = [e for e in telemetry.recent() if e.get("deduped")]
    assert len(deduped_rows) >= 1


def test_budget_exhausted_refuses_call() -> None:
    cfg = fc.load_config()
    cfg["budgets_usd_per_day"]["anthropic"] = 0.0
    fc.save_config(cfg, fc.CONFIG_PATH)
    p = _base_payload()
    p["options"] = {**p["options"], "provider_override": "anthropic"}
    out = dispatcher.dispatch(p)
    assert out["ok"] is False
    assert out["error"] == "budget_exhausted"


def test_budget_resets_at_utc_midnight(
    fabric_reset: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    t0 = 1_700_000_000.0

    def fake_time() -> float:
        return t0

    budget.set_time_fn_for_tests(fake_time)
    cfg = fc.load_config()
    cfg["budgets_usd_per_day"]["anthropic"] = 1.0
    fc.save_config(cfg, fc.CONFIG_PATH)
    budget.reset_for_tests()
    budget.set_time_fn_for_tests(fake_time)
    budget.commit_after_call("anthropic", 0.5)
    assert budget.used_today("anthropic") == 0.5
    t0 += 86400.0
    assert budget.used_today("anthropic") == 0.0


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_receipt_written_for_success(m_url: Any, fabric_reset: Any) -> None:
    m_url.return_value = mocks.anthropic_ok("x", 1, 1)
    out = dispatcher.dispatch(_base_payload())
    path = Path(out["receipt_path"])
    assert path.is_file()
    assert path.suffix == ".json"


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_receipt_written_for_failure(m_url: Any) -> None:
    m_url.side_effect = mocks.http_error(400, "{}")
    out = dispatcher.dispatch(_base_payload())
    assert out["ok"] is False
    assert Path(out["receipt_path"]).is_file()


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_receipt_contains_no_message_content(m_url: Any) -> None:
    m_url.return_value = mocks.anthropic_ok("secret-body", 1, 1)
    out = dispatcher.dispatch(_base_payload())
    raw = Path(out["receipt_path"]).read_text(encoding="utf-8")
    assert "Say hello" not in raw
    assert "secret-body" not in raw


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_receipt_contains_no_plaintext_key(m_url: Any) -> None:
    m_url.return_value = mocks.anthropic_ok("x", 1, 1)
    out = dispatcher.dispatch(_base_payload())
    raw = Path(out["receipt_path"]).read_text(encoding="utf-8")
    assert "sk-ant" not in raw
    assert '"key"' not in raw


def test_receipt_signed_with_existing_axiom_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    keydir = tmp_path / "keys"
    r = runner.invoke(main, ["axiom", "keygen", "--out", str(keydir)])
    assert r.exit_code == 0
    cfgp = tmp_path / "fabric_config.json"
    fc.save_config(fc.default_config(), cfgp)
    monkeypatch.setattr(fc, "CONFIG_PATH", cfgp)
    rdir = tmp_path / "receipts"
    rdir.mkdir(parents=True, exist_ok=True)
    receipts.set_paths_for_tests(
        receipt_dir=rdir, secret_path=keydir / "secret.pem"
    )
    dispatcher.reset_runtime_for_tests()

    with mock.patch(
        "omnix.fabric.providers.common.urllib.request.urlopen",
        return_value=mocks.anthropic_ok("z", 1, 1),
    ):
        out = dispatcher.dispatch(_base_payload())
    jp = Path(out["receipt_path"])
    sp = jp.with_suffix(".sig")
    assert sp.is_file()
    rv = runner.invoke(
        main,
        ["axiom", "verify", str(jp), str(sp), "--pubkey", str(keydir / "public.pem")],
    )
    assert rv.exit_code == 0
    assert "Signature verified successfully" in rv.output


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_receipt_unsigned_when_no_axiom_key(
    m_url: Any, capsys: pytest.CaptureFixture[str], fabric_reset: Any
) -> None:
    receipts.set_paths_for_tests(
        receipt_dir=receipts._RECEIPT_DIR, secret_path=Path("/no/such/secret")
    )
    m_url.return_value = mocks.anthropic_ok("z", 1, 1)
    dispatcher.dispatch(_base_payload())
    err = capsys.readouterr().err
    assert "no-axiom-key-fabric-unsigned-receipt" in err


def test_status_endpoint_returns_snapshot() -> None:
    h = _fh("127.0.0.1", "127.0.0.1:9", "http://127.0.0.1:9")
    with mock.patch("omnix.fabric.handler._send_json") as sj:
        handle_fabric_status_get(h)  # type: ignore[arg-type]
    body = sj.call_args[0][2]
    assert "providers" in body
    for p in ("anthropic", "openai", "google", "ollama"):
        assert p in body["providers"]
        assert "in_flight_count" in body["providers"][p]
    assert "policy" in body
    assert "today_totals" in body


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_google_url_redacted_in_logs(m_url: Any, caplog: pytest.LogCaptureFixture) -> None:
    m_url.return_value = mocks.google_ok()
    caplog.set_level(logging.INFO, logger="omnix.fabric.providers.google")
    p = _base_payload()
    p["provider_key"] = {"provider": "google", "key": "SECRETKEY"}
    p["options"] = {**p["options"], "provider_override": "google"}
    dispatcher.dispatch(p)
    joined = " ".join(caplog.messages)
    assert "SECRETKEY" not in joined
    assert "?key=***" in joined or "key=***" in joined


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_cost_computed_correctly_for_anthropic(m_url: Any) -> None:
    m_url.return_value = mocks.anthropic_ok("x", 1_000_000, 1_000_000)
    dispatcher.dispatch(_base_payload())
    row = telemetry.recent()[-1]
    assert row["cost_usd"] == round(0.80 + 4.00, 6)


def test_spend_endpoint_aggregates_correctly() -> None:
    import datetime as dt

    from omnix.fabric.spend import spend_snapshot

    t = dt.datetime(2026, 4, 24, 12, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    budget.set_time_fn_for_tests(lambda: t)
    budget.reset_for_tests()
    telemetry.reset_for_tests()

    cfg = fc.load_config()
    cap_a = float(cfg["budgets_usd_per_day"]["anthropic"])

    budget.commit_after_call("anthropic", 0.15)
    budget.commit_after_call("anthropic", 0.192)
    budget.commit_after_call("openai", 0.05)

    def row(
        pid: str,
        day: str,
        cost: float,
        tin: int,
        tout: int,
        status: str = "ok",
        tcomplete: str | None = None,
    ) -> dict[str, Any]:
        co = tcomplete or f"{day}T10:00:00Z"
        return {
            "call_id": f"{pid}-{day}-{cost}",
            "agent_id": "a1",
            "provider": pid,
            "model": "m",
            "latency_ms": 1,
            "tokens_in": tin if status == "ok" else 0,
            "tokens_out": tout if status == "ok" else 0,
            "cost_usd": cost if status == "ok" else 0.0,
            "status": status,
            "started_at": f"{day}T09:00:00Z",
            "completed_at": co,
        }

    telemetry.record(
        row(
            "anthropic",
            "2026-04-24",
            0.1,
            4000,
            600,
            tcomplete="2026-04-24T07:55:12Z",
        )
    )
    telemetry.record(
        row(
            "anthropic",
            "2026-04-24",
            0.08,
            4400,
            600,
            tcomplete="2026-04-24T08:01:00Z",
        )
    )
    telemetry.record(row("anthropic", "2026-04-10", 0.50, 100, 50))
    telemetry.record(row("openai", "2026-04-24", 0.02, 100, 20))

    snap = spend_snapshot(cfg)
    a = snap["by_provider"]["anthropic"]
    assert a["today_usd"] == 0.342
    assert a["today_calls"] == 2
    assert a["today_tokens_in"] == 4000 + 4400
    assert a["today_tokens_out"] == 600 + 600
    assert a["month_usd"] == pytest.approx(0.1 + 0.08 + 0.50)
    assert a["month_calls"] == 3
    assert a["last_call_at"] == "2026-04-24T08:01:00Z"
    assert a["budget_cap_today_usd"] == cap_a
    assert a["budget_remaining_today_usd"] == pytest.approx(cap_a - 0.342)

    o = snap["by_provider"]["openai"]
    assert o["today_usd"] == 0.05
    assert o["today_calls"] == 1
    assert o["month_usd"] == pytest.approx(0.02)

    assert snap["totals"]["today_usd"] == pytest.approx(0.392)
    assert snap["totals"]["today_calls"] == 3
    assert snap["totals"]["month_usd"] == pytest.approx(0.68 + 0.02)
    assert snap["computed_at"].startswith("2026-04-24T")

    h = _fh("127.0.0.1", "127.0.0.1:9", "http://127.0.0.1:9")
    with mock.patch("omnix.fabric.handler.load_config", return_value=cfg):
        with mock.patch("omnix.fabric.handler._send_json") as sj:
            handle_fabric_spend_get(h)  # type: ignore[arg-type]
    assert sj.call_args[0][1] == 200
    assert sj.call_args[0][2] == snap


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_thread_pool_concurrency(m_url: Any) -> None:
    def slow(*a: Any, **kw: Any) -> Any:
        time.sleep(0.06)
        return mocks.anthropic_ok("c", 1, 1)

    m_url.side_effect = slow
    ex = ThreadPoolExecutor(max_workers=4)
    futures = [ex.submit(dispatcher.dispatch, _base_payload()) for _ in range(4)]
    for f in futures:
        assert f.result(timeout=30)["ok"] is True
    assert m_url.call_count == 4
    ex.shutdown(wait=False)
