"""
Failure-injection (chaos) suite — Phase 3.1. Adversarial scenarios that must be
handled SAFELY. Every documented disaster class maps to a test here.

Covers SI-3, SI-4, SI-6, SI-8, SI-9, SI-10. These are the go-live blockers.

Skips until the xenalgo execution/broker layer exists. Marked `chaos` so CI can
run them nightly / pre-gate separately from the fast unit suite.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.chaos

execu = pytest.importorskip("xenalgo.execution")


def test_crash_mid_order_no_duplicate_on_restart(mock_broker, tmp_journal):
    """Knight-Capital class: a runaway/duplicate loop must be impossible."""
    cid = "xa-crash-1"
    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
    eng.submit(correlation_id=cid, sleeve="std30", symbol="RELIANCE",
               security_id="2885", side="BUY", qty=10, limit_price=1000.0)
    # Restart 5x — each must adopt, never re-place.
    for _ in range(5):
        e = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
        e.submit(correlation_id=cid, sleeve="std30", symbol="RELIANCE",
                 security_id="2885", side="BUY", qty=10, limit_price=1000.0)
    assert len(mock_broker._orders) == 1


def test_websocket_drop_recovers_fill_via_rest(mock_broker, tmp_journal):
    """Fill confirmation must survive loss of the primary channel."""
    listener = execu.FillListener(broker=mock_broker,
                                  journal=execu.Journal(tmp_journal))
    listener.simulate_ws_drop()
    # A fill happened at the broker while WS was down; REST fallback recovers it.
    mock_broker._orders["xa-ws-1"] = {"broker_order_id": "oid",
                                      "state": "TRADED", "filled_qty": 10,
                                      "avg_price": 1000.0}
    listener.poll_stuck_orders(["xa-ws-1"])
    assert listener.book.qty_for("xa-ws-1") == 10


def test_duplicate_fill_from_redundant_channels_is_noop(mock_broker, tmp_journal):
    listener = execu.FillListener(broker=mock_broker,
                                  journal=execu.Journal(tmp_journal))
    fill = execu.Fill("xa-dup-1", "TCS", "BUY", 5, 3000.0,
                      broker_order_id="oid", event_key="oid:TRADED")
    listener.on_fill(fill)          # from WebSocket
    listener.on_fill(fill)          # same event from Postback webhook
    assert listener.book.qty("TCS") == 5


def test_token_expiry_mid_session_halts_not_crashes(mock_broker, tmp_journal):
    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
    mock_broker.reject_next = True   # broker rejects (simulating auth failure)
    result = eng.submit(correlation_id="xa-tok-1", sleeve="std30",
                        symbol="INFY", security_id="1594", side="BUY",
                        qty=1, limit_price=1500.0)
    # Rejection is recorded, no position created, engine still alive.
    assert result.state == "REJECTED"


def test_rejection_storm_trips_consecutive_failure_breaker(mock_broker, tmp_journal):
    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal),
                                consecutive_failure_halt=3)
    for i in range(3):
        mock_broker.reject_next = True
        eng.submit(correlation_id=f"xa-storm-{i}", sleeve="std30",
                   symbol="INFY", security_id="1594", side="BUY",
                   qty=1, limit_price=1500.0)
    assert eng.is_halted() is True
