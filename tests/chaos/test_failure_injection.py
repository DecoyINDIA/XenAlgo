"""
Failure-injection (chaos) suite — Phase 3.1. Adversarial scenarios that must be
handled SAFELY. Every documented disaster class maps to a test here.

Covers SI-3, SI-4, SI-6, SI-8, SI-9, SI-10. These are the go-live blockers.

Skips until the xenalgo execution/broker layer exists. Marked `chaos` so CI can
run them nightly / pre-gate separately from the fast unit suite.
"""
from __future__ import annotations

import pytest
import datetime as dt
import pandas as pd

pytestmark = pytest.mark.chaos

execu = pytest.importorskip("xenalgo.execution")
data = pytest.importorskip("xenalgo.data")
reconcile = pytest.importorskip("xenalgo.execution.reconcile")
scheduler = pytest.importorskip("xenalgo.scheduler")
token_mod = pytest.importorskip("xenalgo.broker.token")


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
    listener.on_fill(fill)          # same event from REST fallback
    assert listener.book.qty("TCS") == 5


def test_token_expiry_mid_session_halts_not_crashes(mock_broker, tmp_journal):
    """FR-1/SI-6: an expired token blocks the run before order submission."""
    expired = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    token_manager = token_mod.TokenManager(
        tmp_journal,
        token_provider=lambda: token_mod.Token("expired", expired),
    )

    with pytest.raises(token_mod.TradingBlocked):
        token_manager.ensure_valid()
    assert mock_broker._orders == {}


def test_rejection_storm_trips_consecutive_failure_breaker(mock_broker, tmp_journal):
    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal),
                                consecutive_failure_halt=3)
    for i in range(3):
        mock_broker.reject_next = True
        eng.submit(correlation_id=f"xa-storm-{i}", sleeve="std30",
                   symbol="INFY", security_id="1594", side="BUY",
                   qty=1, limit_price=1500.0)
    assert eng.is_halted() is True


def test_corrupt_candle_blocks_trading_before_order(mock_broker):
    """SI-6: NaN/insane candles are rejected before they can drive sizing."""
    panel = {
        "close": pd.DataFrame(
            {"RELIANCE": [1000.0, float("nan")]},
            index=pd.to_datetime(["2026-06-30", "2026-07-01"]),
        )
    }

    with pytest.raises(data.CorruptDataError):
        data.assert_latest_prices_sane(panel, collar_pct=0.03)
    assert mock_broker._orders == {}


def test_reconciliation_drift_halts_trading(mock_broker):
    """SI-8: broker truth wins; any local drift is a halt condition."""
    mock_broker.holdings = {"RELIANCE": 10}
    result = reconcile.Reconciler(mock_broker).reconcile({"RELIANCE": 9})
    assert result.clean is False
    assert result.should_halt is True
    assert result.drift == {"RELIANCE": (9, 10)}


def test_network_partition_records_rejection_not_crash(mock_broker, tmp_journal):
    """NFR-1/SI-9: broker transport failure is journaled and contained."""
    def fail(_req):
        raise ConnectionError("network partition")

    mock_broker.on_place = fail
    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
    result = eng.submit(correlation_id="xa-net-1", sleeve="std30",
                        symbol="INFY", security_id="1594", side="BUY",
                        qty=1, limit_price=1500.0)

    assert result.state == "REJECTED"
    assert "network partition" in result.reason
    states = [event["state"] for event in execu.Journal(tmp_journal).events()]
    assert states == ["INTENT", "SUBMITTED", "REJECTED"]


def test_clock_skew_blocks_scheduler_gate():
    """SI-6/NFR-1: a skewed host clock blocks time-sensitive trading gates."""
    reference = dt.datetime(2026, 7, 1, 15, 5, tzinfo=dt.UTC)
    skewed = reference + dt.timedelta(minutes=7)

    with pytest.raises(scheduler.ClockSkewError):
        scheduler.assert_clock_in_sync(
            now=skewed,
            reference=reference,
            max_skew=dt.timedelta(seconds=30),
        )


@pytest.mark.chaos
def test_one_thousand_restart_replays_are_identical(tmp_journal):
    """SI-3/SI-4/SI-9: 1,000 restart replays retain one cumulative confirmed fill."""
    listener = execu.FillListener(object(), execu.Journal(tmp_journal))
    listener.on_fill(
        execu.Fill(
            correlation_id="restart-1000",
            broker_order_id="paper-1000",
            symbol="SBIN",
            side="BUY",
            filled_qty=10,
            avg_price=100.0,
            event_key="paper-1000:TRADED:10",
        )
    )
    for _ in range(1_000):
        assert execu.PositionBook.from_replay(execu.Journal(tmp_journal)).qty("SBIN") == 10
