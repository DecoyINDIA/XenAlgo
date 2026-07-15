"""B3 mock-only Fyers stream and polling convergence specs. No network or live broker calls."""
from __future__ import annotations

from xenalgo.broker.fyers import (
    FyersGateway,
    FyersOrderFillConsumer,
    FyersOrderStreamAdapter,
    FyersOrderbookPoller,
)
from xenalgo.execution import FillListener, Journal


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def orderbook(self):
        return {"s": "ok", "orderBook": self.rows}


def _fill(qty, status="PART_TRADED"):
    return {
        "id": "fyers-1",
        "tag": "cid-1",
        "symbol": "NSE:SBIN-EQ",
        "side": 1,
        "qty": 10,
        "filledQty": qty,
        "avgTradePrice": 100,
        "status": status,
    }


def test_websocket_and_polling_converge_cumulative_fills(tmp_path):
    listener = FillListener(object(), Journal(tmp_path / "journal.sqlite3"))
    consumer = FyersOrderFillConsumer(listener)
    consumer.on_trade(_fill(4))
    gateway = FyersGateway(FakeClient([_fill(10, "TRADED")]))
    poller = FyersOrderbookPoller(gateway, consumer)

    poller.poll()
    poller.poll()  # duplicate fallback observation is a no-op

    assert listener.book.qty("SBIN") == 10
    assert poller.health()["last_poll_at"] is not None


def test_stream_health_redacts_error_and_reconnects(tmp_path):
    listener = FillListener(object(), Journal(tmp_path / "journal.sqlite3"))
    consumer = FyersOrderFillConsumer(listener)

    class Socket:
        def connect(self):
            return None

        def close_connection(self):
            return None

    adapter = FyersOrderStreamAdapter(lambda **_callbacks: Socket(), consumer)
    adapter.start()
    adapter.on_error(RuntimeError("secret-token-value"))
    assert adapter.health()["last_error"] == "RuntimeError"
    assert "secret-token-value" not in str(adapter.health())
    adapter.reconnect()
    assert adapter.health()["connected"] is True
    assert adapter.health()["reconnects"] == 1


def test_fyers_gateway_order_state_normalization():
    # status 2 = TRADED, status 5 = REJECTED
    raw_order = {
        "id": "fyers-123",
        "tag": "cid-abc",
        "symbol": "NSE:SBIN-EQ",
        "side": 1,
        "qty": 10,
        "filledQty": 10,
        "avgTradePrice": 100.0,
        "status": 2
    }
    gateway = FyersGateway(FakeClient([raw_order]))
    order = gateway.get_order_by_correlation("cid-abc")
    
    assert order is not None
    assert order["state"] == "TRADED"
    assert order["broker_order_id"] == "fyers-123"

