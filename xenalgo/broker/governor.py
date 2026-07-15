import datetime as dt
import time

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def default_ist_date() -> dt.date:
    return dt.datetime.now(IST).date()


class TokenBucket:
    def __init__(
        self,
        rate_per_sec: float,
        capacity: int | None = None,
        clock=time.monotonic,
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be positive")
        self.rate_per_sec = float(rate_per_sec)
        self.capacity = int(capacity if capacity is not None else rate_per_sec)
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        self._clock = clock
        self._tokens = float(self.capacity)
        self._last = float(self._clock())

    def try_acquire(self, tokens: int = 1) -> bool:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        now = float(self._clock())
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(
            float(self.capacity),
            self._tokens + elapsed * self.rate_per_sec,
        )
        if self._tokens + 1e-12 < tokens:
            return False
        self._tokens -= tokens
        return True


class OrderGovernor:
    def __init__(
        self,
        max_per_sec: float = 2,
        max_per_day: int = 500,
        clock=time.monotonic,
        date_provider=default_ist_date,
    ) -> None:
        if max_per_sec > 2:
            raise ValueError("order governor must stay at or below 2 orders/sec")
        self.max_per_sec = float(max_per_sec)
        self.max_per_day = int(max_per_day)
        self._used_today = 0
        self.bucket = TokenBucket(rate_per_sec=self.max_per_sec, clock=clock)
        self._date_provider = date_provider
        self._current_date = self._date_provider()

    def _check_reset(self) -> None:
        today = self._date_provider()
        if today != self._current_date:
            self._used_today = 0
            self._current_date = today

    def allow(self) -> bool:
        self._check_reset()
        if self._used_today >= self.max_per_day:
            return False
        if not self.bucket.try_acquire():
            return False
        self._used_today += 1
        return True

    def remaining_today(self) -> int:
        self._check_reset()
        return max(0, self.max_per_day - self._used_today)
