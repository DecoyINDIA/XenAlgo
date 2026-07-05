from __future__ import annotations

import time


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
    def __init__(self, max_per_sec: float = 2, max_per_day: int = 500) -> None:
        if max_per_sec > 2 or max_per_sec >= 10:
            raise ValueError("order governor must stay at or below 2 orders/sec")
        self.max_per_sec = float(max_per_sec)
        self.max_per_day = int(max_per_day)
        self._used_today = 0
        self.bucket = TokenBucket(rate_per_sec=self.max_per_sec)

    def allow(self) -> bool:
        if self._used_today >= self.max_per_day:
            return False
        self._used_today += 1
        return True

    def remaining_today(self) -> int:
        return max(0, self.max_per_day - self._used_today)
