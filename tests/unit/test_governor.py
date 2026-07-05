"""
Executable specification for xenalgo.broker.governor (rate limiter).

Covers: SI-5 (order rate <=2/s, <= daily cap), SI-12 (provably below SEBI
10-OPS threshold). Requirement FR-7 governor.

The governor is the single choke point for outgoing orders (TRD §2.1). Strategy
code cannot bypass it. Uses an injected clock so tests are deterministic.

Skips until xenalgo.broker.governor exists (Phase 1).
"""
from __future__ import annotations

import pytest

gov = pytest.importorskip("xenalgo.broker.governor")


class ManualClock:
    def __init__(self, t=0.0):
        self.t = t
    def monotonic(self):
        return self.t
    def tick(self, dt):
        self.t += dt


def test_never_exceeds_two_per_second():
    clk = ManualClock()
    g = gov.TokenBucket(rate_per_sec=2, clock=clk.monotonic)
    # Two immediate grants, third must wait.
    assert g.try_acquire() is True
    assert g.try_acquire() is True
    assert g.try_acquire() is False
    clk.tick(0.5)                    # +1 token at 2/s
    assert g.try_acquire() is True
    assert g.try_acquire() is False


def test_burst_of_100_stays_under_cap():
    clk = ManualClock()
    g = gov.TokenBucket(rate_per_sec=2, clock=clk.monotonic)
    granted, total_time = 0, 0.0
    for _ in range(100):
        while not g.try_acquire():
            clk.tick(0.01)
            total_time += 0.01
        granted += 1
    assert granted == 100
    # 100 orders at <=2/s must take >= ~49.5s of simulated time.
    assert total_time >= 49.0
    # Include the bucket's two-token startup allowance when checking long-run rate.
    startup_allowance_seconds = 2 / g.rate_per_sec
    assert granted / max(total_time + startup_allowance_seconds, 1e-9) <= 2.0 + 1e-6


def test_daily_cap_enforced():
    g = gov.OrderGovernor(max_per_sec=2, max_per_day=500)
    for _ in range(500):
        assert g.allow() is True
    assert g.allow() is False        # 501st blocked
    assert g.remaining_today() == 0


def test_well_below_sebi_threshold():
    # Design invariant: configured rate must be < 10 OPS by a wide margin.
    g = gov.OrderGovernor(max_per_sec=2, max_per_day=500)
    assert g.max_per_sec <= 2 < 10
