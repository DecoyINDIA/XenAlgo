from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from xenalgo.execution import Fill, FillListener, Journal
from xenalgo.ops import KillSwitch
from xenalgo.config import load_config
from xenalgo.web import ConsoleStore, TelegramCommandRouter, create_app, runtime_from_config


def _seed_traded_order(tmp_journal: str) -> ConsoleStore:
    journal = Journal(tmp_journal)
    journal.append(
        correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
        state="INTENT",
        sleeve="std30",
        symbol="RELIANCE",
        security_id="2885",
        side="BUY",
        intended_qty=10,
        limit_price=1000.0,
    )
    journal.append(
        correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
        state="PENDING",
        broker_order_id="paper-1",
        sleeve="std30",
        symbol="RELIANCE",
        security_id="2885",
        side="BUY",
        intended_qty=10,
        limit_price=1000.0,
    )
    FillListener(broker=None, journal=journal).on_fill(
        Fill(
            correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
            broker_order_id="paper-1",
            symbol="RELIANCE",
            side="BUY",
            filled_qty=10,
            avg_price=1000.0,
            event_key="paper-1:TRADED",
        )
    )
    return ConsoleStore(tmp_journal)


def test_console_snapshot_replays_journal_positions(tmp_journal):
    store = _seed_traded_order(tmp_journal)

    snapshot = store.snapshot()

    assert snapshot["summary"]["open_orders"] == 0
    assert snapshot["summary"]["positions"] == 1
    assert snapshot["positions"] == [
        {
            "symbol": "RELIANCE",
            "qty": 10,
            "avg_price": 1000.0,
            "sleeves": ["std30"],
            "updated_utc": snapshot["positions"][0]["updated_utc"],
        }
    ]
    assert snapshot["orders"][0]["state"] == "TRADED"


def test_console_snapshot_treats_partial_fills_as_cumulative(tmp_journal):
    journal = Journal(tmp_journal)
    fill_listener = FillListener(broker=None, journal=journal)
    fill_listener.on_fill(
        Fill(
            correlation_id="xa-cumulative",
            broker_order_id="paper-cumulative",
            symbol="SBIN",
            side="BUY",
            filled_qty=4,
            avg_price=600.0,
            event_key="paper-cumulative:PART_TRADED:4",
            state="PART_TRADED",
        )
    )
    fill_listener.on_fill(
        Fill(
            correlation_id="xa-cumulative",
            broker_order_id="paper-cumulative",
            symbol="SBIN",
            side="BUY",
            filled_qty=10,
            avg_price=601.0,
            event_key="paper-cumulative:TRADED:10",
        )
    )
    fill_listener.on_fill(
        Fill(
            correlation_id="xa-cumulative",
            broker_order_id="paper-cumulative",
            symbol="SBIN",
            side="BUY",
            filled_qty=10,
            avg_price=601.0,
            event_key="paper-cumulative:TRADED:10-duplicate-channel",
        )
    )

    snapshot = ConsoleStore(tmp_journal).snapshot()

    assert snapshot["positions"] == [
        {
            "symbol": "SBIN",
            "qty": 10,
            "avg_price": 601.0,
            "sleeves": ["unknown"],
            "updated_utc": snapshot["positions"][0]["updated_utc"],
        }
    ]


def test_dashboard_snapshot_and_sse_surface_paper_fill(tmp_journal):
    store = _seed_traded_order(tmp_journal)
    client = TestClient(create_app(store, control_token="secret"))

    page = client.get("/")
    assert page.status_code == 200
    assert "XenAlgo Console" in page.text
    assert "RELIANCE" in page.text

    snapshot = client.get("/api/snapshot").json()
    assert snapshot["positions"][0]["symbol"] == "RELIANCE"

    sse = client.get("/events?once=true")
    assert sse.status_code == 200
    assert sse.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in sse.text
    assert "RELIANCE" in sse.text


def test_dashboard_kill_switch_requires_auth_and_blocks_submission_fast(tmp_journal):
    store = ConsoleStore(tmp_journal)
    client = TestClient(create_app(store, control_token="secret"))

    assert client.post("/control/kill").status_code == 401

    started = time.monotonic()
    response = client.post(
        "/control/kill?source=dashboard&actor=operator",
        headers={"X-XenAlgo-Console-Token": "secret"},
    )
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 1.0
    assert KillSwitch(tmp_journal).allow_submission() is False
    snapshot = store.snapshot()
    assert snapshot["risk_state"][0]["key"] == "kill_switch"
    assert snapshot["audit"][0]["action"] == "kill_switch.activate"


def test_breaker_rearm_requires_auth_and_is_audited(tmp_journal):
    store = ConsoleStore(tmp_journal)
    store.set_breaker("drawdown_halt", actor="test")
    client = TestClient(create_app(store, control_token="secret"))

    response = client.post(
        "/control/rearm/drawdown_halt?actor=operator&reason=reviewed",
        headers={"X-XenAlgo-Console-Token": "secret"},
    )

    assert response.status_code == 200
    snapshot = store.snapshot()
    assert snapshot["risk_state"] == []
    assert snapshot["audit"][0]["action"] == "breaker.rearm"
    assert "drawdown_halt" in snapshot["audit"][0]["detail"]


def test_postback_endpoint_is_removed_for_fyers_order_ws(tmp_journal):
    store = ConsoleStore(tmp_journal)
    client = TestClient(create_app(store, control_token="secret"))

    assert client.post("/postback", content=json.dumps({}).encode("utf-8")).status_code == 404


def test_telegram_command_router_status_kill_positions_and_rearm(tmp_journal):
    store = _seed_traded_order(tmp_journal)
    router = TelegramCommandRouter(store)

    assert "Unknown command" in router.handle("")
    assert "1 positions" in router.handle("/status")
    assert "RELIANCE: 10 @ 1000.0" in router.handle("/positions")
    assert "Kill switch active" in router.handle("/kill", actor="telegram-user")
    assert KillSwitch(tmp_journal).allow_submission() is False
    assert "Re-armed kill_switch" in router.handle("/rearm kill_switch", actor="telegram-user")
    assert store.snapshot()["risk_state"] == []


def test_web_runtime_requires_token_and_rejects_public_wildcard_bind():
    config = load_config("live")

    try:
        runtime_from_config(config, env={"TAILSCALE_BIND_HOST": "127.0.0.1"})
    except ValueError as exc:
        assert "XENALGO_CONSOLE_TOKEN" in str(exc)
    else:
        raise AssertionError("missing console token should fail closed")

    try:
        runtime_from_config(
            config,
            env={
                "TAILSCALE_BIND_HOST": "0.0.0.0",
                "XENALGO_CONSOLE_TOKEN": "secret",
            },
        )
    except ValueError as exc:
        assert "loopback or a Tailscale" in str(exc)
    else:
        raise AssertionError("public wildcard bind should fail closed")

    try:
        runtime_from_config(
            config,
            env={
                "TAILSCALE_BIND_HOST": "8.8.8.8",
                "XENALGO_CONSOLE_TOKEN": "secret",
            },
        )
    except ValueError as exc:
        assert "loopback or a Tailscale" in str(exc)
    else:
        raise AssertionError("public IP bind should fail closed")

    runtime = runtime_from_config(
        config,
        env={
            "TAILSCALE_BIND_HOST": "100.64.0.10",
            "XENALGO_CONSOLE_TOKEN": "secret",
        },
    )
    assert runtime.host == "100.64.0.10"
    assert runtime.port == 8080
    assert runtime.control_token == "secret"
