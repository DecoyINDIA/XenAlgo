from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from xenalgo.broker.fyers import FyersGateway, FyersOrderFillConsumer, FyersSymbolResolver, fyers_payload_to_fill
from xenalgo.broker.token import FyersOAuthProvider, TokenManager, TradingBlocked, token_store_excluded_from_backup
from xenalgo.data import FyersHistoryLoader, panels_match_validated_baseline
from xenalgo.execution import FillListener, Journal
from xenalgo.risk import OrderRequest
from xenalgo.web import ConsoleStore, create_app, runtime_from_config
from xenalgo.web.server import build_app_from_config
from xenalgo.config import load_config


def test_bind_guard_rejects_public_ip_and_allows_loopback_tailscale():
    config = load_config("live")
    base_env = {"XENALGO_CONSOLE_TOKEN": "secret"}

    assert runtime_from_config(config, env={**base_env, "TAILSCALE_BIND_HOST": "127.0.0.1"}).host == "127.0.0.1"
    assert runtime_from_config(config, env={**base_env, "TAILSCALE_BIND_HOST": "100.100.1.2"}).host == "100.100.1.2"

    for host in ["0.0.0.0", "::", "8.8.8.8"]:
        with pytest.raises(ValueError):
            runtime_from_config(config, env={**base_env, "TAILSCALE_BIND_HOST": host})


def test_public_postback_endpoint_removed(tmp_journal):
    client = TestClient(create_app(ConsoleStore(tmp_journal), control_token="secret"))

    assert client.post("/postback", json={}).status_code == 404


def test_fyers_order_ws_applies_fill_idempotently(tmp_journal):
    listener = FillListener(broker=None, journal=Journal(tmp_journal))
    consumer = FyersOrderFillConsumer(listener)
    payload = {
        "id": "fy-1",
        "tag": "cid-fy-1",
        "symbol": "NSE:SBIN-EQ",
        "side": 1,
        "qty": 10,
        "filledQty": 10,
        "avgTradePrice": 600.0,
        "status": "TRADED",
    }

    consumer.on_trade(payload)
    consumer.on_trade(payload)

    assert listener.book.qty("SBIN") == 10


def test_orderbook_poll_backfills_missed_fill(tmp_journal):
    listener = FillListener(broker=None, journal=Journal(tmp_journal))
    consumer = FyersOrderFillConsumer(listener)

    consumer.poll_orderbook([
        {
            "id": "fy-2",
            "tag": "cid-fy-2",
            "symbol": "NSE:RELIANCE-EQ",
            "side": 1,
            "qty": 8,
            "filledQty": 8,
            "avgTradePrice": 2500.0,
            "status": "FILLED",
        }
    ])

    assert listener.book.qty("RELIANCE") == 8


class _FyersClient:
    def __init__(self) -> None:
        self.placed = []
        self.modified = []
        self.cancelled = []

    def place_order(self, payload):
        self.placed.append(payload)
        return {"s": "ok", "id": "fy-order-1"}

    def orderbook(self):
        return {"orderBook": []}

    def modify_order(self, payload):
        self.modified.append(payload)
        return {"s": "ok"}

    def cancel_order(self, payload):
        self.cancelled.append(payload)
        return {"message": "closed"}

    def holdings(self):
        return {"holdings": []}

    def positions(self):
        return {"positions": []}

    def funds(self):
        return {"fund_limit": []}


def test_fyers_gateway_places_maps_and_is_idempotent_by_tag():
    client = _FyersClient()
    gateway = FyersGateway(client)
    req = OrderRequest("cid-order", "std30", "RELIANCE", "NSE:RELIANCE-EQ", "BUY", 3, 2500.0)

    first = gateway.place_order(req)
    second = gateway.place_order(req)

    assert first.status == "PENDING"
    assert second.status == "DUPLICATE"
    assert client.placed == [
        {
            "symbol": "NSE:RELIANCE-EQ",
            "qty": 3,
            "type": 1,
            "side": 1,
            "productType": "CNC",
            "limitPrice": 2500.0,
            "stopPrice": 0,
            "validity": "DAY",
            "offlineOrder": False,
            "tag": "cid-order",
        }
    ]


def test_fyers_symbol_resolution():
    assert FyersSymbolResolver().resolve("SBIN") == "NSE:SBIN-EQ"
    assert FyersSymbolResolver({"SBIN": "NSE:SBIN-BE"}).resolve("sbin") == "NSE:SBIN-BE"


def test_fyers_gateway_orderbook_lookup_modify_cancel_and_passthroughs():
    class Client(_FyersClient):
        def orderbook(self):
            return {"orderBook": [{"id": "fy-existing", "orderTag": "cid-existing"}]}

    client = Client()
    gateway = FyersGateway(client)

    assert gateway.get_order_by_correlation("cid-existing")["id"] == "fy-existing"
    assert gateway.modify_order("fy-existing", qty=5, limit_price=100.5).status == "PENDING"
    assert client.modified == [{"id": "fy-existing", "qty": 5, "limitPrice": 100.5}]
    assert gateway.cancel_order("fy-existing").status == "REJECTED"
    assert gateway.get_orderbook() == [{"id": "fy-existing", "orderTag": "cid-existing"}]
    assert gateway.get_holdings() == {"holdings": []}
    assert gateway.get_positions() == {"positions": []}
    assert gateway.get_funds() == {"fund_limit": []}


def test_fyers_gateway_rejection_and_market_sell_payload():
    class Client(_FyersClient):
        def place_order(self, payload):
            self.placed.append(payload)
            return {"s": "error", "message": "bad order"}

    client = Client()
    gateway = FyersGateway(client, order_type="MARKET")
    req = OrderRequest("cid-sell", "std30", "SBIN", "NSE:SBIN-EQ", "SELL", 2, 600.0)

    ack = gateway.place_order(req)

    assert ack.status == "REJECTED"
    assert ack.reason == "bad order"
    assert client.placed[0]["type"] == 2
    assert client.placed[0]["side"] == -1
    assert client.placed[0]["limitPrice"] == 0


def test_fyers_payload_variants_and_ignored_updates():
    assert fyers_payload_to_fill({"filledQty": 0, "tag": "cid"}) is None
    assert fyers_payload_to_fill({"filledQty": 1}) is None

    fill = fyers_payload_to_fill(
        {
            "order_id": "fy-3",
            "correlation_id": "cid-3",
            "tradingSymbol": "INFY",
            "transactionType": "SELL",
            "quantity": 10,
            "tradedQty": 4,
            "tradedPrice": 1500.0,
            "status": "PART_TRADED",
        }
    )

    assert fill is not None
    assert fill.state == "PART_TRADED"
    assert fill.side == "SELL"
    assert fill.symbol == "INFY"


def test_token_store_excluded_from_backup_manifest(tmp_path):
    token_store = tmp_path / ".xenalgo-secrets" / "fyers_token.sqlite"
    token_store.parent.mkdir()
    assert token_store_excluded_from_backup(token_store, [tmp_path / "Diary"])
    assert not token_store_excluded_from_backup(token_store, [tmp_path])


def test_fyers_token_provider_returns_valid_token(tmp_path):
    now = dt.datetime(2026, 7, 11, tzinfo=dt.UTC)

    class Session:
        def set_token(self, auth_code):
            self.auth_code = auth_code

        def generate_token(self):
            return {"access_token": "token-from-fyers"}

    provider = FyersOAuthProvider(
        auth_code_provider=lambda: "auth-code",
        session_factory=Session,
        clock=lambda: now,
    )
    manager = TokenManager(tmp_path / "fyers_token.sqlite", provider, clock=lambda: now)

    token = manager.ensure_valid()

    assert token.value == "token-from-fyers"
    assert token.expires_at > now
    assert manager.ensure_valid().value == "token-from-fyers"


def test_expired_fyers_token_blocks_trading(tmp_path):
    now = dt.datetime(2026, 7, 11, tzinfo=dt.UTC)
    manager = TokenManager(
        tmp_path / "fyers_token.sqlite",
        token_provider=lambda: SimpleNamespace(value="expired", expires_at=now - dt.timedelta(seconds=1)),
        clock=lambda: now,
    )

    with pytest.raises(TradingBlocked):
        manager.ensure_valid()


def test_fyers_token_provider_blocks_missing_auth_or_access_token(tmp_path):
    now = dt.datetime(2026, 7, 11, tzinfo=dt.UTC)

    class EmptySession:
        def set_token(self, auth_code):
            self.auth_code = auth_code

        def generate_token(self):
            return {"message": "denied"}

    no_auth = FyersOAuthProvider(auth_code_provider=lambda: "", session_factory=EmptySession, clock=lambda: now)
    no_token = FyersOAuthProvider(auth_code_provider=lambda: "auth", session_factory=EmptySession, clock=lambda: now)

    for provider in [no_auth, no_token]:
        with pytest.raises(TradingBlocked):
            provider()


def test_brain_executor_has_no_live_order_route():
    from Brain.executor import LiveExecutor

    with pytest.raises(RuntimeError, match="quarantined"):
        LiveExecutor({"live_trading": {}, "backtest": {"initial_capital": 1}, "portfolio": {}}, mode="live")
    assert not (Path(__file__).resolve().parents[2] / "Brain" / "order_manager.py").exists()


def test_fyers_history_loader_chunks_and_normalizes_daily_rows():
    class Client:
        def __init__(self):
            self.calls = []

        def history(self, payload):
            self.calls.append(payload)
            return {"candles": [[1_672_531_200, 10, 11, 9, 10.5, 1000]]}

    client = Client()
    loader = FyersHistoryLoader(client)
    df = loader.history("SBIN", dt.date(2023, 1, 1), dt.date(2024, 2, 1))

    assert len(client.calls) == 2
    assert df.iloc[0]["symbol"] == "SBIN"
    assert df.iloc[0]["security_id"] == "NSE:SBIN-EQ"


def test_build_app_from_config_and_invalid_bind_host(tmp_path):
    config = load_config("live")
    with pytest.raises(ValueError, match="must be an IP address"):
        runtime_from_config(config, env={"TAILSCALE_BIND_HOST": "not-a-host", "XENALGO_CONSOLE_TOKEN": "secret"})

    root = Path(__file__).resolve().parents[2]
    temp_root = tmp_path / "root"
    (temp_root / "config").mkdir(parents=True)
    live_config = (root / "config" / "config.live.yaml").read_text(encoding="utf-8")
    live_config = live_config.replace("Diary/state/order_journal.sqlite", "state/order_journal.sqlite")
    (temp_root / "config" / "config.live.yaml").write_text(live_config, encoding="utf-8")
    (temp_root / "state").mkdir()

    app = build_app_from_config(root=temp_root, env={"XENALGO_CONSOLE_TOKEN": "secret"})
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_fyers_panel_matches_validated_baseline():
    baseline = pd.DataFrame(
        [{"symbol": "SBIN", "date": dt.date(2026, 7, 10), "open": 100, "high": 102, "low": 99, "close": 101}]
    )
    candidate = pd.DataFrame(
        [{"symbol": "SBIN", "date": dt.date(2026, 7, 10), "open": 100.01, "high": 102.01, "low": 99.0, "close": 101.01}]
    )

    ok, failures = panels_match_validated_baseline(baseline, candidate, tolerance_bps=5)

    assert ok
    assert failures == []
