"""
Shared pytest fixtures and test doubles for XenAlgo.

These support the executable-specification tests in tests/unit/. Modules under
`xenalgo.*` are built in Phase 1; until then the spec tests skip via
`pytest.importorskip`. The doubles here are dependency-free so the harness is
usable the moment implementation begins.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Callable, Optional

import pytest


IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


class FakeClock:
    """Deterministic clock for scheduler/window/token tests."""

    def __init__(self, now: _dt.datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        self._now = now

    def now(self) -> _dt.datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now = self._now + _dt.timedelta(**kwargs)

    def set(self, now: _dt.datetime) -> None:
        self._now = now if now.tzinfo else now.replace(tzinfo=IST)


@dataclass
class _Ack:
    status: str
    broker_order_id: Optional[str]
    correlation_id: str
    reason: str = ""


@dataclass
class MockBroker:
    """
    Programmable in-memory BrokerInterface double.

    Configure fills, rejections, and latency to drive execution/fill tests
    without any network. Mirrors the BrokerInterface contract in TRD §4.
    """
    holdings: dict = field(default_factory=dict)      # symbol -> qty
    positions: dict = field(default_factory=dict)     # symbol -> qty
    cash: float = 10_000_000.0
    _orders: dict = field(default_factory=dict)       # correlation_id -> dict
    reject_next: bool = False
    on_place: Optional[Callable] = None               # hook(req) -> None
    _seq: int = 0

    def place_order(self, req) -> _Ack:
        # Idempotency: if correlation_id already seen, return existing ack.
        cid = getattr(req, "correlation_id", None) or req["correlation_id"]
        if cid in self._orders:
            o = self._orders[cid]
            return _Ack("DUPLICATE", o["broker_order_id"], cid)
        if self.on_place:
            self.on_place(req)
        if self.reject_next:
            self.reject_next = False
            self._orders[cid] = {"broker_order_id": None, "state": "REJECTED"}
            return _Ack("REJECTED", None, cid, reason="injected rejection")
        self._seq += 1
        oid = f"mock-{self._seq}"
        self._orders[cid] = {"broker_order_id": oid, "state": "PENDING"}
        return _Ack("PENDING", oid, cid)

    def get_order_by_correlation(self, cid: str):
        return self._orders.get(cid)

    def get_holdings(self):
        return [{"tradingSymbol": s, "totalQty": q} for s, q in self.holdings.items()]

    def get_positions(self):
        return [{"tradingSymbol": s, "netQty": q} for s, q in self.positions.items()]

    def get_funds(self):
        return {"availabelBalance": self.cash}


@pytest.fixture
def ist_clock():
    # A normal trading Wednesday, mid execution window.
    return FakeClock(_dt.datetime(2026, 7, 1, 15, 5, tzinfo=IST))


@pytest.fixture
def mock_broker():
    return MockBroker()


@pytest.fixture
def tmp_journal(tmp_path):
    """Path to a throwaway SQLite journal DB for durability/state tests."""
    return str(tmp_path / "xenalgo_test.sqlite")


@pytest.fixture
def base_risk_config():
    return {
        "max_order_notional_inr": 200_000,
        "max_pct_of_adv": 0.05,
        "price_collar_pct": 0.03,
        "max_position_pct": 0.10,
        "max_positions_global": 40,
        "daily_loss_halt_pct": 0.02,
        "drawdown_halt_pct": 0.10,
        "consecutive_failure_halt": 3,
    }
