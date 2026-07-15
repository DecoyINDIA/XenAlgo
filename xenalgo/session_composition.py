from __future__ import annotations

import datetime as dt
import importlib
import json
import logging
from typing import Any, Callable, Iterable

import pandas as pd

from xenalgo.broker.fyers import FyersSymbolResolver
from xenalgo.config import RuntimeConfig
from xenalgo.data import FyersHistoryLoader, assert_panel_fresh, validate_history_frame
from xenalgo.execution import Journal
from xenalgo.execution.reconcile import Reconciler
from xenalgo.monolith import PaperOrderPlan
from xenalgo.strategy import SleeveAllocator

logger = logging.getLogger("QuantPlatform.SessionComposition")


def get_sleeve_positions(journal: Journal, sleeve: str) -> dict[str, int]:
    qty: dict[str, int] = {}
    seen = set()
    cumulative_qty_by_order = {}
    for event in journal.events():
        if event["sleeve"] != sleeve:
            continue
        if event["state"] not in {"PART_TRADED", "TRADED"} or not event["filled_qty"]:
            continue
        raw = json.loads(event["raw_json"] or "{}")
        event_key = raw.get("event_key") or f"{event['event_id']}"
        if event_key in seen:
            continue
        seen.add(event_key)
        order_key = event["broker_order_id"] or event["correlation_id"]
        cumulative_qty = int(event["filled_qty"])
        previous_qty = cumulative_qty_by_order.get(order_key, 0)
        delta_qty = max(cumulative_qty - previous_qty, 0)
        cumulative_qty_by_order[order_key] = max(previous_qty, cumulative_qty)
        sign = 1 if event["side"].upper() == "BUY" else -1
        qty[event["symbol"]] = qty.get(event["symbol"], 0) + sign * delta_qty
    return {symbol: q for symbol, q in qty.items() if q != 0}


def build_panel_provider(
    config: RuntimeConfig,
    client: Any,
    symbols: list[str],
    warmup_days: int = 150,
) -> Callable[[dt.date], dict]:
    loader = FyersHistoryLoader(client)

    def panel_provider(trading_date: dt.date) -> dict:
        start_date = trading_date - dt.timedelta(days=warmup_days)
        close_dfs = []
        volume_dfs = []
        open_dfs = []
        high_dfs = []
        low_dfs = []

        for symbol in symbols:
            df = loader.history(symbol, start_date, trading_date)
            validate_history_frame(df, start=start_date, end=trading_date)

            df_sorted = df.sort_values("date")
            index = pd.DatetimeIndex(pd.to_datetime(df_sorted["date"]))

            close_s = pd.Series(df_sorted["close"].values, index=index, name=symbol)
            volume_s = pd.Series(df_sorted["volume"].values, index=index, name=symbol)
            open_s = pd.Series(df_sorted["open"].values, index=index, name=symbol)
            high_s = pd.Series(df_sorted["high"].values, index=index, name=symbol)
            low_s = pd.Series(df_sorted["low"].values, index=index, name=symbol)

            close_dfs.append(close_s)
            volume_dfs.append(volume_s)
            open_dfs.append(open_s)
            high_dfs.append(high_s)
            low_dfs.append(low_s)

        close_df = pd.concat(close_dfs, axis=1).sort_index()
        volume_df = pd.concat(volume_dfs, axis=1).sort_index()
        open_df = pd.concat(open_dfs, axis=1).sort_index()
        high_df = pd.concat(high_dfs, axis=1).sort_index()
        low_df = pd.concat(low_dfs, axis=1).sort_index()

        panel = {
            "close": close_df,
            "volume": volume_df,
            "open": open_df,
            "high": high_df,
            "low": low_df,
        }
        assert_panel_fresh(panel, trading_date)
        return panel

    return panel_provider


def build_order_provider(
    config: RuntimeConfig,
    journal: Journal,
    reconciler: Reconciler,
) -> Callable[[dt.date, dict], Iterable[PaperOrderPlan]]:
    from Brain.portfolio_engine import PortfolioEngine

    def order_provider(trading_date: dt.date, panel: dict) -> Iterable[PaperOrderPlan]:
        sleeves_cfg = config.data.get("sleeves", {})
        enabled_sleeves = {
            name: float(cfg["capital_fraction"])
            for name, cfg in sleeves_cfg.items()
            if cfg.get("enabled", True)
        }

        close = panel["close"]
        previous_close = {symbol: float(close[symbol].iloc[-1]) for symbol in close.columns}
        portfolio_value = reconciler.portfolio_value(previous_close)

        sleeve_allocator = SleeveAllocator(portfolio_value, enabled_sleeves)
        pe = PortfolioEngine(config.data)
        resolver = FyersSymbolResolver()

        plans = []
        for sleeve in enabled_sleeves:
            try:
                module = importlib.import_module(f"Strategies.{sleeve}")
            except ImportError as e:
                logger.error(f"Failed to import strategy {sleeve}: {e}")
                continue

            factor_scores = module.compute(panel)
            target_weights = pe.generate_target_weights(factor_scores, panel)

            if target_weights.empty:
                continue
            targets = target_weights.iloc[-1]

            current_shares = get_sleeve_positions(journal, sleeve)
            sleeve_cap = sleeve_allocator.capital(sleeve)

            target_shares = {}
            for sym in targets.index:
                w = targets[sym]
                px = previous_close.get(sym, 0.0)
                if pd.isna(px) or px <= 0:
                    continue
                target_shares[sym] = int((w * sleeve_cap) / px)

            symbols_union = set(targets.index) | set(current_shares.keys())
            for sym in symbols_union:
                t_qty = target_shares.get(sym, 0)
                c_qty = current_shares.get(sym, 0)
                delta = t_qty - c_qty
                if delta != 0:
                    side = "BUY" if delta > 0 else "SELL"
                    qty = abs(delta)
                    limit_price = previous_close.get(sym, 0.0)
                    cid = f"{sleeve}:{sym}:{trading_date.isoformat()}"
                    sec_id = resolver.resolve(sym)
                    plans.append(
                        PaperOrderPlan(
                            correlation_id=cid,
                            sleeve=sleeve,
                            symbol=sym,
                            security_id=sec_id,
                            side=side,
                            qty=qty,
                            limit_price=limit_price,
                        )
                    )
        return plans

    return order_provider
