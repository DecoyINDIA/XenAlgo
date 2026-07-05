"""
Executable specification for xenalgo.risk.RiskEngine.

Covers safety invariants: SI-1 (max notional), SI-2 (position cap),
SI-4 (duplicate), SI-6 (stale/corrupt data), SI-7 (drawdown re-arm).
Requirements: FR-9, FR-10, FR-19.

The RiskEngine is a PURE veto layer (TRD §2.5): given an order + context it
returns (decision, allowed_qty, reason) with no I/O. Strategy code cannot bypass
it — every order in ExecutionEngine passes through check().

Skips until xenalgo.risk exists (Phase 1).
"""
from __future__ import annotations

import pytest

risk = pytest.importorskip("xenalgo.risk")


def _order(**kw):
    base = dict(
        correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
        sleeve="std30", symbol="RELIANCE", security_id="2885",
        side="BUY", qty=10, limit_price=1000.0,
    )
    base.update(kw)
    return risk.OrderRequest(**base)


def _ctx(**kw):
    base = dict(
        portfolio_value=10_000_000.0,
        positions={},                       # symbol -> {"qty","avg_price"}
        adv={"RELIANCE": 1_000_000},        # 20-day avg daily volume (shares)
        prev_close={"RELIANCE": 1000.0},
        cash=10_000_000.0,
        restricted=set(),
        seen_correlation_ids=set(),
        breakers={},                        # e.g. {"drawdown_halt": True}
    )
    base.update(kw)
    return risk.RiskContext(**base)


# ── SI-1: max order notional ─────────────────────────────────────────────
def test_rejects_order_over_max_notional(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    # 300 sh * 1000 = 300,000 > 200,000 cap
    decision, qty, reason = eng.check(_order(qty=300), _ctx())
    assert decision is risk.RiskDecision.REJECT
    assert "notional" in reason.lower()


def test_allows_order_within_notional(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    decision, qty, _ = eng.check(_order(qty=100), _ctx())
    assert decision is risk.RiskDecision.ALLOW
    assert qty == 100


# ── SI-2: per-position 10% cap (scale-down, not silent reject) ───────────
def test_scales_down_to_position_cap(base_risk_config):
    cfg = dict(base_risk_config, max_order_notional_inr=2_000_000)
    eng = risk.RiskEngine(cfg)
    # cap = 10% of 10M = 1,000,000 -> 1000 sh @ 1000; ask for 2000
    decision, qty, reason = eng.check(_order(qty=2000), _ctx())
    assert decision is risk.RiskDecision.SCALE
    assert qty == 1000
    assert "10%" in reason or "position" in reason.lower()


# ── SI-4: duplicate detection via correlationId ──────────────────────────
def test_rejects_duplicate_correlation_id(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    cid = "xa-20260701-std30-RELIANCE-BUY-1"
    ctx = _ctx(seen_correlation_ids={cid})
    decision, _, reason = eng.check(_order(correlation_id=cid), ctx)
    assert decision is risk.RiskDecision.REJECT
    assert "duplicate" in reason.lower()


# ── liquidity: <=5% of ADV ───────────────────────────────────────────────
def test_rejects_order_exceeding_adv_cap(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    # 5% of 1,000,000 ADV = 50,000 shares; ask for 60,000
    decision, qty, reason = eng.check(
        _order(qty=60_000, limit_price=1.0), _ctx()
    )
    assert decision in (risk.RiskDecision.REJECT, risk.RiskDecision.SCALE)
    if decision is risk.RiskDecision.SCALE:
        assert qty <= 50_000


# ── price collar: reject insane prices from bad data ─────────────────────
def test_rejects_price_outside_collar(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    # prev_close 1000, collar 3% -> limit 1100 is outside
    decision, _, reason = eng.check(_order(limit_price=1100.0, qty=10), _ctx())
    assert decision is risk.RiskDecision.REJECT
    assert "collar" in reason.lower() or "price" in reason.lower()


# ── SI-6: restricted list (ASM/GSM/circuit/blacklist) blocks entries ─────
def test_rejects_restricted_symbol(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    ctx = _ctx(restricted={"RELIANCE"})
    decision, _, reason = eng.check(_order(), ctx)
    assert decision is risk.RiskDecision.REJECT
    assert "restrict" in reason.lower()


# ── cash sufficiency with fee buffer ─────────────────────────────────────
def test_rejects_when_insufficient_cash(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    ctx = _ctx(cash=5_000.0)  # can't afford 10 * 1000
    decision, _, reason = eng.check(_order(qty=10), ctx)
    assert decision in (risk.RiskDecision.REJECT, risk.RiskDecision.SCALE)


# ── SI-7: breakers veto everything ───────────────────────────────────────
@pytest.mark.parametrize("breaker", [
    "drawdown_halt", "daily_loss_halt", "kill_switch", "stale_data",
    "reconciliation_mismatch",
])
def test_any_active_breaker_rejects_all_orders(base_risk_config, breaker):
    eng = risk.RiskEngine(base_risk_config)
    ctx = _ctx(breakers={breaker: True})
    decision, _, reason = eng.check(_order(), ctx)
    assert decision is risk.RiskDecision.REJECT
    assert breaker.split("_")[0] in reason.lower() or "halt" in reason.lower()


# ── purity: check() must not mutate its inputs ───────────────────────────
def test_check_is_pure(base_risk_config):
    eng = risk.RiskEngine(base_risk_config)
    ctx = _ctx()
    seen_before = set(ctx.seen_correlation_ids)
    eng.check(_order(), ctx)
    assert ctx.seen_correlation_ids == seen_before
