"""
NSE market schedule checker — IST-aware.

Equity cash market hours: 9:15 AM – 3:30 PM IST, Monday–Friday.
"""
import datetime
import logging

logger = logging.getLogger("QuantPlatform.MarketHours")

# NSE equity market hours in IST
MARKET_OPEN = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)

_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon–Fri


def _now_ist() -> datetime.datetime:
    """Current time in IST (UTC+5:30)."""
    utc = datetime.datetime.now(datetime.timezone.utc)
    return utc.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def is_market_open() -> bool:
    """Returns True during NSE equity cash hours (9:15-15:30 IST, Mon-Fri)."""
    now = _now_ist()
    if now.weekday() not in _WEEKDAYS:
        return False
    t = now.time()
    return MARKET_OPEN <= t < MARKET_CLOSE


def minutes_to_close() -> int:
    """Minutes remaining until 3:30 PM IST. Returns 0 if already closed or weekend."""
    if not is_market_open():
        return 0
    now = _now_ist()
    close_dt = now.replace(hour=MARKET_CLOSE.hour, minute=MARKET_CLOSE.minute, second=0, microsecond=0)
    diff = (close_dt - now).total_seconds()
    return max(0, int(diff // 60))


def next_market_open() -> datetime.datetime:
    """Returns the next market open datetime in IST."""
    now = _now_ist()
    current = now
    for _ in range(14):  # at most 2 weeks ahead
        current = current.replace(hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute, second=0, microsecond=0)
        current += datetime.timedelta(days=1)
        if current.weekday() in _WEEKDAYS:
            return current
    return current  # fallback


def market_status() -> str:
    """Human-readable market status string."""
    if is_market_open():
        mins = minutes_to_close()
        return f"🟢 MARKET OPEN — {mins} min to close"
    now = _now_ist()
    if now.weekday() in _WEEKDAYS and now.time() < MARKET_OPEN:
        return "🔴 MARKET CLOSED — opens at 9:15 AM IST"
    if now.weekday() in _WEEKDAYS:
        return "🔴 MARKET CLOSED — closed at 3:30 PM IST"
    return "🔴 WEEKEND"
