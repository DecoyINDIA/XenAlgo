from __future__ import annotations

import math
import datetime as dt
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from xenalgo.broker.fyers import FyersSymbolResolver, default_fyers_history_chunks


class StaleDataError(RuntimeError):
    pass


class CorruptDataError(RuntimeError):
    pass


class DataService:
    """Single-writer daily dataset boundary with fail-closed validation."""

    _writer_lock = threading.Lock()

    def __init__(self, loader: "FyersHistoryLoader") -> None:
        self.loader = loader

    def ingest(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        if not self._writer_lock.acquire(blocking=False):
            raise RuntimeError("market-data writer already active")
        try:
            frame = self.loader.history(symbol, start, end)
            validate_history_frame(frame, start=start, end=end)
            return frame
        finally:
            self._writer_lock.release()


@dataclass(frozen=True)
class DataParityReport:
    passed: bool
    material_differences: tuple[str, ...]
    baseline_rows: int
    candidate_rows: int


@dataclass(frozen=True)
class RestrictedSnapshot:
    symbols: frozenset[str]
    fetched_at: dt.datetime
    source: str

    def require_fresh(self, now: dt.datetime, max_age: dt.timedelta) -> frozenset[str]:
        if not self.source.strip():
            raise StaleDataError("restricted-symbol source is missing")
        if now - self.fetched_at > max_age:
            raise StaleDataError("restricted-symbol snapshot is stale")
        return self.symbols


class FyersHistoryLoader:
    def __init__(self, client: Any, *, symbol_resolver: FyersSymbolResolver | None = None) -> None:
        self.client = client
        self.symbol_resolver = symbol_resolver or FyersSymbolResolver()

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        frames = []
        for chunk_start, chunk_end in default_fyers_history_chunks(start, end):
            response = self.client.history(
                {
                    "symbol": self.symbol_resolver.resolve(symbol),
                    "resolution": "D",
                    "date_format": "1",
                    "range_from": chunk_start.isoformat(),
                    "range_to": chunk_end.isoformat(),
                    "cont_flag": "1",
                }
            )
            candles = response.get("candles") or response.get("data", {}).get("candles") or []
            if candles:
                frames.append(_candles_to_frame(symbol, candles))
        if not frames:
            return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume", "security_id"])
        return pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"], keep="last")


def _candles_to_frame(symbol: str, candles: list[list[float]]) -> pd.DataFrame:
    rows = []
    for candle in candles:
        ts, open_, high, low, close, volume = candle[:6]
        rows.append(
            {
                "symbol": symbol,
                "date": pd.to_datetime(ts, unit="s").date() if isinstance(ts, (int, float)) else pd.to_datetime(ts).date(),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": int(volume),
                "security_id": FyersSymbolResolver().resolve(symbol),
            }
        )
    return pd.DataFrame(rows)


def synthetic_mode_for_fyers(config: dict[str, Any]) -> bool:
    fyers = config.get("fyers") or config.get("broker", {})
    required = ["app_id", "secret_key"]
    return any(not fyers.get(key) or str(fyers.get(key)).startswith("YOUR_") for key in required)


def panels_match_validated_baseline(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    tolerance_bps: float = 5.0,
) -> tuple[bool, list[str]]:
    merged = baseline.merge(candidate, on=["symbol", "date"], suffixes=("_base", "_candidate"))
    failures: list[str] = []
    tolerance = tolerance_bps / 10_000
    for _, row in merged.iterrows():
        for field in ["open", "high", "low", "close"]:
            base = float(row[f"{field}_base"])
            other = float(row[f"{field}_candidate"])
            if base and abs(base - other) / base > tolerance:
                failures.append(f"{row['symbol']} {row['date']} {field}")
    baseline_universe = set(baseline["symbol"].unique())
    candidate_universe = set(candidate["symbol"].unique())
    if baseline_universe != candidate_universe:
        failures.append("universe membership mismatch")
    return not failures, failures


def data_parity_report(
    baseline: pd.DataFrame, candidate: pd.DataFrame, *, tolerance_bps: float = 5.0
) -> DataParityReport:
    passed, failures = panels_match_validated_baseline(
        baseline, candidate, tolerance_bps=tolerance_bps
    )
    return DataParityReport(passed, tuple(failures), len(baseline), len(candidate))


def validate_history_frame(frame: pd.DataFrame, *, start: date, end: date) -> None:
    required = {"symbol", "date", "open", "high", "low", "close", "volume", "security_id"}
    missing = required - set(frame.columns)
    if missing:
        raise CorruptDataError(f"history columns missing: {', '.join(sorted(missing))}")
    if frame.empty:
        raise StaleDataError("history response is empty")
    if frame.duplicated(["symbol", "date"]).any():
        raise CorruptDataError("history contains duplicate symbol/date rows")
    dates = pd.to_datetime(frame["date"]).dt.date
    if dates.min() < start or dates.max() > end:
        raise CorruptDataError("history contains rows outside the requested range")
    numeric = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or (numeric[["open", "high", "low", "close"]] <= 0).any().any():
        raise CorruptDataError("history contains non-numeric or non-positive prices")
    if (numeric["high"] < numeric[["open", "close", "low"]].max(axis=1)).any():
        raise CorruptDataError("history high is below OHLC values")
    if (numeric["low"] > numeric[["open", "close", "high"]].min(axis=1)).any():
        raise CorruptDataError("history low is above OHLC values")


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


def assert_latest_prices_sane(panel: dict, sanity_move_pct: float = 0.25) -> None:
    close = panel.get("close")
    if close is None or close.empty:
        raise CorruptDataError("panel has no close data")

    latest = close.iloc[-1]
    previous = close.iloc[-2] if len(close.index) >= 2 else latest
    for symbol, price in latest.items():
        if not price_is_sane(price, previous[symbol], sanity_move_pct):
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
