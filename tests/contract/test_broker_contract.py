"""
BrokerInterface contract coverage.

Covers Phase 1 tasks 1.5/1.6 at the safe boundary: PaperBroker must behave like
the gateway contract without any live Fyers order API access. FyersGateway coverage
uses injected/mocked clients only.
"""
from __future__ import annotations

from types import SimpleNamespace

from xenalgo.broker.paper import PaperBroker


def _request(
    *,
    correlation_id: str = "xa-20260701-std30-RELIANCE-BUY-1",
    symbol: str = "RELIANCE",
    security_id: str = "2885",
    side: str = "BUY",
    qty: int = 10,
    limit_price: float = 1000.0,
):
    return SimpleNamespace(
        correlation_id=correlation_id,
        symbol=symbol,
        security_id=security_id,
        side=side,
        qty=qty,
        limit_price=limit_price,
    )


def test_paper_broker_is_idempotent_by_correlation_id():
    broker = PaperBroker(cash=1_000_000.0)
    req = _request()

    first = broker.place_order(req)
    second = broker.place_order(req)

    assert first.status == "PENDING"
    assert second.status == "DUPLICATE"
    assert second.broker_order_id == first.broker_order_id
    assert len(broker._orders) == 1


def test_paper_broker_fill_uses_requested_qty_and_updates_holdings_from_fill_only():
    broker = PaperBroker(cash=1_000_000.0, ltp={"RELIANCE": 1000.0})
    ack = broker.place_order(_request(qty=7))

    assert broker.get_holdings() == []

    broker.mark_filled(ack.correlation_id)

    order = broker.get_order_by_id(ack.broker_order_id)
    assert order["state"] == "TRADED"
    assert order["filled_qty"] == 7
    assert broker.holdings["RELIANCE"] == 7
    assert broker.cash == 993_000.0


def test_paper_broker_rejected_order_cannot_be_filled():
    broker = PaperBroker(cash=1_000.0, ltp={"RELIANCE": 1000.0})
    ack = broker.place_order(_request(qty=10))

    assert ack.status == "REJECTED"

    broker.mark_filled(ack.correlation_id)

    assert broker.get_order_by_id(ack.broker_order_id)["state"] == "REJECTED"
    assert broker.get_holdings() == []


def test_paper_broker_cancel_blocks_later_fill():
    broker = PaperBroker(cash=1_000_000.0, ltp={"RELIANCE": 1000.0})
    ack = broker.place_order(_request())

    cancel = broker.cancel_order(ack.broker_order_id)
    broker.mark_filled(ack.correlation_id)

    assert cancel.status == "CANCELLED"
    assert broker.get_order_by_id(ack.broker_order_id)["state"] == "CANCELLED"
    assert broker.get_holdings() == []


def test_paper_broker_modify_updates_pending_request():
    broker = PaperBroker(cash=1_000_000.0, ltp={"RELIANCE": 950.0})
    ack = broker.place_order(_request(qty=10, limit_price=1000.0))

    modify = broker.modify_order(ack.broker_order_id, qty=12, limit_price=950.0)
    broker.mark_filled(ack.correlation_id)

    order = broker.get_order_by_id(ack.broker_order_id)
    assert modify.status == "PENDING"
    assert order["filled_qty"] == 12
    assert order["avg_price"] == 950.0
    assert broker.cash == 988_600.0
