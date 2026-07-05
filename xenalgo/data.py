from __future__ import annotations

import math
from datetime import date


class StaleDataError(RuntimeError):
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


def price_is_sane(value: float, prev_close: float, collar_pct: float) -> bool:
    try:
        price = float(value)
        prev = float(prev_close)
    except (TypeError, ValueError):
        return False
    if math.isnan(price) or price <= 0 or prev <= 0:
        return False
    return abs(price - prev) / prev <= float(collar_pct)
