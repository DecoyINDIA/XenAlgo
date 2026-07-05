from __future__ import annotations

import math
from datetime import date


class StaleDataError(RuntimeError):
    pass


class CorruptDataError(RuntimeError):
    pass


class DataService:
    pass


def _as_date(value) -> date:
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def assert_panel_fresh(panel: dict, expected_trading_date: str | date) -> None:
    close = panel.get("close")
    if close is None or close.empty:
        raise StaleDataError("panel has no close data")
    latest = _as_date(close.index.max())
    expected = _as_date(expected_trading_date)
    if latest != expected:
        raise StaleDataError(f"stale panel: latest={latest}, expected={expected}")


def assert_latest_prices_sane(panel: dict, collar_pct: float) -> None:
    close = panel.get("close")
    if close is None or close.empty:
        raise CorruptDataError("panel has no close data")

    latest = close.iloc[-1]
    previous = close.iloc[-2] if len(close.index) >= 2 else latest
    for symbol, price in latest.items():
        if not price_is_sane(price, previous[symbol], collar_pct):
            raise CorruptDataError(f"corrupt close for {symbol}")


def price_is_sane(value: float, prev_close: float, collar_pct: float) -> bool:
    try:
        price = float(value)
        prev = float(prev_close)
    except (TypeError, ValueError):
        return False
    if math.isnan(price) or price <= 0 or prev <= 0:
        return False
    return abs(price - prev) / prev <= float(collar_pct)
