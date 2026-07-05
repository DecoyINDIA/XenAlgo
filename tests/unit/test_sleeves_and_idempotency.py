"""
Executable specifications for capital sleeves and end-to-end order idempotency.

Covers: sleeve capital isolation (fixes the 3-alphas-fight-over-100% bug),
cross-sleeve netting, and SI-4 (no duplicate order for the same correlationId
across a simulated crash-restart). Requirements FR-4, FR-5, FR-6.

Skips until the respective xenalgo modules exist (Phase 1).
"""
from __future__ import annotations

import pytest


# ─────────────────────────── Sleeves ────────────────────────────────────
strategy = pytest.importorskip("xenalgo.strategy")


def test_sleeve_sizes_against_its_own_capital():
    sleeves = strategy.SleeveAllocator(
        total_capital=9_000_000.0,
        fractions={"std30": 0.34, "alpha_027": 0.33, "alpha_062": 0.33},
    )
    assert sleeves.capital("std30") == pytest.approx(3_060_000.0)
    assert sleeves.capital("alpha_027") == pytest.approx(2_970_000.0)
    # Sum of sleeve capitals never exceeds total (no over-allocation).
    assert sum(sleeves.capital(s) for s in sleeves.names) <= 9_000_000.0 + 1e-6


def test_fractions_must_not_exceed_one():
    with pytest.raises(ValueError):
        strategy.SleeveAllocator(
            total_capital=1_000_000.0,
            fractions={"a": 0.6, "b": 0.6},          # 1.2 > 1.0
        )


def test_cross_sleeve_netting():
    """Sleeve A sells 10 RELIANCE, sleeve B buys 10 -> net zero orders."""
    net = strategy.net_targets([
        {"sleeve": "std30", "symbol": "RELIANCE", "delta": -10},
        {"sleeve": "alpha_027", "symbol": "RELIANCE", "delta": +10},
    ])
    assert net.get("RELIANCE", 0) == 0


def test_netting_preserves_nonzero():
    net = strategy.net_targets([
        {"sleeve": "std30", "symbol": "TCS", "delta": +5},
        {"sleeve": "alpha_027", "symbol": "TCS", "delta": +3},
    ])
    assert net["TCS"] == 8


# ─────────────────────── End-to-end idempotency ─────────────────────────
execu = pytest.importorskip("xenalgo.execution")


def test_no_double_order_across_1000_restart_attempts(mock_broker, tmp_journal):
    """
    Submit an order, simulate a crash BEFORE the ack is journaled, restart,
    and re-run the same target 1,000 times. The gateway must adopt the
    existing order via correlationId, not place a second one.
    """
    calls = []
    mock_broker.on_place = lambda req: calls.append(req)
    cid = "xa-20260701-std30-RELIANCE-BUY-1"

    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
    eng.submit(correlation_id=cid, sleeve="std30", symbol="RELIANCE",
               security_id="2885", side="BUY", qty=10, limit_price=1000.0)

    # Simulate crash + fresh process using the SAME journal + broker state.
    for _ in range(1000):
        eng2 = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
        eng2.submit(correlation_id=cid, sleeve="std30", symbol="RELIANCE",
                    security_id="2885", side="BUY", qty=10, limit_price=1000.0)

    # Broker saw exactly one order for this correlation id.
    assert len(mock_broker._orders) == 1
    assert len(calls) == 1


def test_place_order_hook_called_once_per_correlation(mock_broker, tmp_journal):
    calls = []
    mock_broker.on_place = lambda req: calls.append(req)
    cid = "xa-20260701-std30-INFY-BUY-1"
    eng = execu.ExecutionEngine(broker=mock_broker, journal=execu.Journal(tmp_journal))
    eng.submit(correlation_id=cid, sleeve="std30", symbol="INFY",
               security_id="1594", side="BUY", qty=1, limit_price=1500.0)
    eng.submit(correlation_id=cid, sleeve="std30", symbol="INFY",
               security_id="1594", side="BUY", qty=1, limit_price=1500.0)
    assert len(calls) == 1
