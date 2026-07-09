from __future__ import annotations

import pandas as pd

from Brain.walk_forward import WalkForwardValidator, anchored_windows


def _config(costs: bool = False) -> dict:
    return {
        "backtest": {"initial_capital": 100000.0},
        "portfolio": {
            "type": "LongOnly",
            "rebalance_freq": "Daily",
            "max_positions": 1,
            "sizing": "EqualWeight",
            "min_liquidity_days": 1,
            "min_trade_value": 0,
        },
        "universe": {"min_price": 1.0, "min_volume": 1.0},
        "costs": {
            "brokerage_pct": 0.00001 if costs else 0.0,
            "stt_buy_pct": 0.0,
            "stt_sell_pct": 0.0,
            "exchange_charges_pct": 0.0,
            "gst_pct": 0.18,
            "stamp_duty_pct": 0.0,
            "sebi_charges_pct": 0.0,
            "slippage_pct": 0.0,
        },
    }


def _panel() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    dates = pd.bdate_range("2026-01-01", periods=12)
    prices = pd.DataFrame(
        {
            "ALPHA": [100, 101, 102, 103, 105, 107, 109, 111, 113, 115, 117, 119],
            "BETA": [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89],
        },
        index=dates,
        dtype=float,
    )
    panel = {
        "open": prices.copy(),
        "high": prices * 1.01,
        "low": prices * 0.99,
        "close": prices.copy(),
        "volume": pd.DataFrame(100000.0, index=dates, columns=prices.columns),
    }
    factors = pd.DataFrame({"ALPHA": 1.0, "BETA": 0.0}, index=dates)
    return panel, factors


def test_anchored_windows_expand_training_set_and_keep_test_slices_out_of_sample():
    dates = pd.bdate_range("2026-01-01", periods=12)

    windows = anchored_windows(dates, train_bars=4, test_bars=3)

    assert [(w.train_end, w.test_start, w.test_end) for w in windows] == [
        (dates[3], dates[4], dates[6]),
        (dates[6], dates[7], dates[9]),
        (dates[9], dates[10], dates[11]),
    ]
    assert all(window.train_end < window.test_start for window in windows)
    assert all(window.train_start == dates[0] for window in windows)


def test_walk_forward_runs_existing_cost_aware_backtester_on_each_test_window():
    panel, factors = _panel()

    report = WalkForwardValidator(_config()).run(
        factors,
        panel,
        train_bars=4,
        test_bars=3,
    )

    payload = report.as_dict()
    assert payload["aggregate"]["window_count"] == 3
    assert payload["aggregate"]["test_bars"] == 8
    assert payload["aggregate"]["total_trades"] >= 3
    assert payload["aggregate"]["median_total_return_pct"] > 0
    assert all(window["metrics"]["final_value"] > 100000.0 for window in payload["windows"])


def test_walk_forward_reports_transaction_cost_drag_when_configured():
    panel, factors = _panel()

    report = WalkForwardValidator(_config(costs=True)).run(
        factors,
        panel,
        train_bars=4,
        test_bars=3,
        include_partial=False,
    )

    assert report.aggregate["window_count"] == 2
    assert report.aggregate["total_transaction_costs"] > 0
    assert all(result.metrics["cost_drag_pct"] > 0 for result in report.windows)
