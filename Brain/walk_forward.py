from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from Brain.backtest_engine import BacktestEngine
from Brain.portfolio_engine import PortfolioEngine


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def as_dict(self) -> dict[str, str]:
        return {
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
        }


@dataclass(frozen=True)
class WindowResult:
    window: WalkForwardWindow
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "window": self.window.as_dict(),
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class WalkForwardReport:
    windows: list[WindowResult]
    aggregate: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "windows": [window.as_dict() for window in self.windows],
            "aggregate": self.aggregate,
        }


def anchored_windows(
    dates: Iterable[pd.Timestamp],
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    include_partial: bool = True,
) -> list[WalkForwardWindow]:
    """Create anchored walk-forward windows from an ordered trading calendar."""
    if train_bars <= 0:
        raise ValueError("train_bars must be positive")
    if test_bars <= 0:
        raise ValueError("test_bars must be positive")
    if step_bars is not None and step_bars <= 0:
        raise ValueError("step_bars must be positive")

    idx = pd.DatetimeIndex(dates).drop_duplicates().sort_values()
    if len(idx) <= train_bars:
        return []

    step = step_bars or test_bars
    windows: list[WalkForwardWindow] = []
    train_end_pos = train_bars - 1
    while train_end_pos + 1 < len(idx):
        test_start_pos = train_end_pos + 1
        test_end_pos = min(test_start_pos + test_bars - 1, len(idx) - 1)
        if not include_partial and test_end_pos - test_start_pos + 1 < test_bars:
            break
        windows.append(
            WalkForwardWindow(
                train_start=idx[0],
                train_end=idx[train_end_pos],
                test_start=idx[test_start_pos],
                test_end=idx[test_end_pos],
            )
        )
        train_end_pos += step
    return windows


class WalkForwardValidator:
    """
    Runs anchored walk-forward validation using the existing research engines.

    The validator does not train or tune parameters itself. It validates that a
    supplied point-in-time factor panel survives repeated out-of-sample slices
    while preserving PortfolioEngine's one-bar signal lag and BacktestEngine's
    transaction-cost model.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def run(
        self,
        factor_scores: pd.DataFrame,
        panel: Dict[str, pd.DataFrame],
        *,
        train_bars: int,
        test_bars: int,
        step_bars: int | None = None,
        benchmark_series: Optional[pd.Series] = None,
        include_partial: bool = True,
    ) -> WalkForwardReport:
        _require_panel(panel)
        dates = panel["close"].index
        windows = anchored_windows(
            dates,
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step_bars,
            include_partial=include_partial,
        )

        results: list[WindowResult] = []
        for window in windows:
            research_panel = _slice_panel(panel, window.train_start, window.test_end)
            research_factors = factor_scores.loc[window.train_start : window.test_end]
            target_weights = PortfolioEngine(self.config).generate_target_weights(
                research_factors,
                research_panel,
            )
            test_weights = target_weights.loc[window.test_start : window.test_end]
            test_panel = _slice_panel(panel, window.test_start, window.test_end)
            benchmark = (
                benchmark_series.loc[window.test_start : window.test_end]
                if benchmark_series is not None
                else None
            )
            backtest = BacktestEngine(self.config).run(test_weights, test_panel, benchmark)
            results.append(WindowResult(window=window, metrics=_metrics(backtest, self.config)))

        return WalkForwardReport(windows=results, aggregate=_aggregate(results))


def _require_panel(panel: Dict[str, pd.DataFrame]) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(panel)
    if missing:
        raise ValueError(f"panel missing required frames: {sorted(missing)}")
    if panel["close"].empty:
        raise ValueError("panel close frame must not be empty")


def _slice_panel(
    panel: Dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Dict[str, pd.DataFrame]:
    return {name: frame.loc[start:end].copy() for name, frame in panel.items()}


def _metrics(backtest: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    history = backtest["history"]
    trades = backtest["trades"]
    initial_capital = float(config["backtest"].get("initial_capital", 1.0))
    final_value = float(history["portfolio_value"].iloc[-1])
    returns = history["returns"].astype(float)
    total_return = final_value / initial_capital - 1.0
    volatility = float(returns.std(ddof=0) * math.sqrt(252))
    sharpe = 0.0 if volatility == 0 else float((returns.mean() * 252) / volatility)
    equity = history["portfolio_value"].astype(float)
    drawdown = (equity / equity.cummax()) - 1.0
    max_drawdown = float(abs(drawdown.min()))
    trade_count = int(len(trades))
    costs = float(trades["costs"].sum()) if trade_count and "costs" in trades else 0.0
    gross_notional = float(trades["value"].abs().sum()) if trade_count and "value" in trades else 0.0
    return {
        "bars": int(len(history)),
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return * 100.0, 6),
        "annualized_volatility_pct": round(volatility * 100.0, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown_pct": round(max_drawdown * 100.0, 6),
        "trade_count": trade_count,
        "gross_notional": round(gross_notional, 2),
        "transaction_costs": round(costs, 2),
        "cost_drag_pct": round((costs / initial_capital) * 100.0, 6),
    }


def _aggregate(results: List[WindowResult]) -> dict[str, Any]:
    if not results:
        return {
            "window_count": 0,
            "test_bars": 0,
            "mean_sharpe": None,
            "median_total_return_pct": None,
            "worst_max_drawdown_pct": None,
            "total_trades": 0,
            "total_transaction_costs": 0.0,
        }

    metrics = [result.metrics for result in results]
    returns = pd.Series([item["total_return_pct"] for item in metrics], dtype=float)
    return {
        "window_count": len(results),
        "test_bars": int(sum(item["bars"] for item in metrics)),
        "mean_sharpe": round(sum(item["sharpe"] for item in metrics) / len(metrics), 6),
        "median_total_return_pct": round(float(returns.median()), 6),
        "worst_max_drawdown_pct": round(max(item["max_drawdown_pct"] for item in metrics), 6),
        "total_trades": int(sum(item["trade_count"] for item in metrics)),
        "total_transaction_costs": round(sum(item["transaction_costs"] for item in metrics), 2),
    }
