"""
Executable specifications for the Reconciler and DataService gates.

Covers: SI-8 (state reconciles to broker truth or halts), SI-6 (no trading on
stale/corrupt data), and the CNC-in-holdings correctness fix. Requirements
FR-11, FR-3.

Two independent test modules folded together because they share the broker
double and panel fixtures.

Skips until the respective xenalgo modules exist (Phase 1).
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd
import pytest


# ─────────────────────────── Reconciler ─────────────────────────────────
reconcile = pytest.importorskip("xenalgo.execution.reconcile")


def test_swing_positions_read_from_holdings_not_positions(mock_broker):
    """CNC delivery positions live in holdings; the old bug read get_positions."""
    mock_broker.holdings = {"RELIANCE": 50, "TCS": 10}
    mock_broker.positions = {}            # intraday empty for overnight swing
    r = reconcile.Reconciler(mock_broker)
    truth = r.broker_truth_positions()
    assert truth["RELIANCE"] == 50
    assert truth["TCS"] == 10


def test_broker_truth_merges_intraday_positions(mock_broker):
    mock_broker.holdings = {"RELIANCE": 50}
    mock_broker.positions = {"RELIANCE": -5, "INFY": 3}
    r = reconcile.Reconciler(mock_broker)

    assert r.broker_truth_positions() == {"RELIANCE": 45, "INFY": 3}


def test_detects_drift_and_signals_halt(mock_broker):
    mock_broker.holdings = {"RELIANCE": 50}
    r = reconcile.Reconciler(mock_broker)
    local = {"RELIANCE": 49}              # 1-share drift
    result = r.reconcile(local)
    assert result.clean is False
    assert result.should_halt is True


def test_clean_when_matching(mock_broker):
    mock_broker.holdings = {"RELIANCE": 50}
    r = reconcile.Reconciler(mock_broker)
    result = r.reconcile({"RELIANCE": 50})
    assert result.clean is True
    assert result.should_halt is False


def test_portfolio_value_is_cash_plus_marked_holdings(mock_broker):
    mock_broker.holdings = {"RELIANCE": 10}
    mock_broker.cash = 1_000_000.0
    r = reconcile.Reconciler(mock_broker)
    pv = r.portfolio_value(ltp={"RELIANCE": 1000.0})
    assert pv == pytest.approx(1_000_000.0 + 10 * 1000.0)


# ─────────────────────────── DataService ────────────────────────────────
data = pytest.importorskip("xenalgo.data")

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


def _panel(last_date: str):
    idx = pd.to_datetime([last_date])
    close = pd.DataFrame({"RELIANCE": [1000.0]}, index=idx)
    return {"close": close, "open": close, "high": close, "low": close,
            "volume": pd.DataFrame({"RELIANCE": [10000]}, index=idx)}


def test_fresh_panel_passes_gate():
    svc = data.DataService.__new__(data.DataService)   # gate is a pure method
    data.assert_panel_fresh(_panel("2026-07-01"),
                            expected_trading_date="2026-07-01")


def test_stale_panel_blocks_trading():
    with pytest.raises(data.StaleDataError):
        data.assert_panel_fresh(_panel("2026-06-28"),
                                expected_trading_date="2026-07-01")


@pytest.mark.parametrize("bad", [float("nan"), 0.0, -5.0])
def test_price_sanity_rejects_bad_values(bad):
    assert data.price_is_sane(bad, prev_close=1000.0, collar_pct=0.03) is False


def test_price_sanity_rejects_out_of_collar():
    assert data.price_is_sane(1100.0, prev_close=1000.0, collar_pct=0.03) is False


def test_price_sanity_accepts_normal():
    assert data.price_is_sane(1010.0, prev_close=1000.0, collar_pct=0.03) is True


def test_history_validation_and_restricted_snapshot_fail_closed():
    frame = pd.DataFrame(
        [{
            "symbol": "SBIN", "date": _dt.date(2026, 7, 1), "open": 100,
            "high": 102, "low": 99, "close": 101, "volume": 1_000,
            "security_id": "NSE:SBIN-EQ",
        }]
    )
    data.validate_history_frame(frame, start=_dt.date(2026, 7, 1), end=_dt.date(2026, 7, 1))
    report = data.data_parity_report(frame, frame.copy())
    assert report.passed is True
    assert report.baseline_rows == report.candidate_rows == 1

    now = _dt.datetime(2026, 7, 2, tzinfo=_dt.UTC)
    snapshot = data.RestrictedSnapshot(
        frozenset({"ABC"}), now - _dt.timedelta(hours=1), "exchange-list"
    )
    assert snapshot.require_fresh(now, _dt.timedelta(hours=2)) == frozenset({"ABC"})
    with pytest.raises(data.StaleDataError, match="stale"):
        snapshot.require_fresh(now, _dt.timedelta(minutes=30))


def test_history_validation_rejects_duplicate_and_invalid_ohlc():
    row = {
        "symbol": "SBIN", "date": _dt.date(2026, 7, 1), "open": 100,
        "high": 90, "low": 99, "close": 101, "volume": 1_000,
        "security_id": "NSE:SBIN-EQ",
    }
    with pytest.raises(data.CorruptDataError, match="duplicate"):
        data.validate_history_frame(
            pd.DataFrame([row, row]), start=_dt.date(2026, 7, 1), end=_dt.date(2026, 7, 1)
        )
    with pytest.raises(data.CorruptDataError, match="high"):
        data.validate_history_frame(
            pd.DataFrame([row]), start=_dt.date(2026, 7, 1), end=_dt.date(2026, 7, 1)
        )
