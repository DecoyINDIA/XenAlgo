from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, time


class ClockSkewError(RuntimeError):
    pass


class MarketCalendar:
    def __init__(self, overrides: dict[date, str] | None = None) -> None:
        self.overrides = overrides or {}

    def is_trading_day(self, day: date) -> bool:
        if day in self.overrides:
            return False
        return day.weekday() < 5


@dataclass(frozen=True)
class ExecutionWindow:
    start: str = "15:00"
    end: str = "15:20"
    block_open_until: str = "09:30"

    def is_open(self, value: time) -> bool:
        start = _parse_hhmm(self.start)
        end = _parse_hhmm(self.end)
        return start <= value <= end


@dataclass(frozen=True)
class RebalancePlan:
    freq: str
    day: int

    def is_rebalance_day(self, value: date) -> bool:
        if self.freq.lower() == "weekly":
            return value.weekday() == self.day
        if self.freq.lower() == "daily":
            return True
        raise ValueError(f"unsupported rebalance frequency: {self.freq}")


def assert_clock_in_sync(now: datetime, reference: datetime, max_skew: timedelta) -> None:
    if now.tzinfo is None or reference.tzinfo is None:
        raise ClockSkewError("clock check requires timezone-aware timestamps")
    skew = abs(now - reference)
    if skew > max_skew:
        raise ClockSkewError(f"clock skew {skew} exceeds {max_skew}")


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))
