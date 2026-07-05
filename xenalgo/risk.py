from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class RiskDecision(Enum):
    ALLOW = auto()
    REJECT = auto()
    SCALE = auto()


@dataclass(frozen=True)
class OrderRequest:
    correlation_id: str
    sleeve: str
    symbol: str
    security_id: str
    side: str
    qty: int
    limit_price: float


@dataclass(frozen=True)
class RiskContext:
    portfolio_value: float
    positions: dict[str, dict] = field(default_factory=dict)
    adv: dict[str, float] = field(default_factory=dict)
    prev_close: dict[str, float] = field(default_factory=dict)
    cash: float = 0.0
    restricted: set[str] = field(default_factory=set)
    seen_correlation_ids: set[str] = field(default_factory=set)
    breakers: dict[str, bool] = field(default_factory=dict)


class RiskEngine:
    def __init__(self, config: dict) -> None:
        self.config = dict(config)

    def check(self, order: OrderRequest, ctx: RiskContext):
        if order.qty <= 0:
            return RiskDecision.REJECT, 0, "quantity must be positive"
        if order.limit_price <= 0:
            return RiskDecision.REJECT, 0, "price must be positive"

        for breaker, active in ctx.breakers.items():
            if active:
                return RiskDecision.REJECT, 0, f"{breaker} halt active"

        if order.correlation_id in ctx.seen_correlation_ids:
            return RiskDecision.REJECT, 0, "duplicate correlationId"

        if order.symbol in ctx.restricted:
            return RiskDecision.REJECT, 0, "restricted symbol"

        prev_close = ctx.prev_close.get(order.symbol)
        collar_pct = float(self.config.get("price_collar_pct", 0.03))
        if prev_close is None or prev_close <= 0:
            return RiskDecision.REJECT, 0, "missing previous close"
        if abs(order.limit_price - prev_close) / prev_close > collar_pct:
            return RiskDecision.REJECT, 0, "price outside collar"

        qty = order.qty
        decision = RiskDecision.ALLOW
        reasons: list[str] = []

        adv = ctx.adv.get(order.symbol)
        max_adv_pct = float(self.config.get("max_pct_of_adv", 0.05))
        if adv is not None:
            max_adv_qty = int(adv * max_adv_pct)
            if max_adv_qty <= 0:
                return RiskDecision.REJECT, 0, "ADV cap is zero"
            if qty > max_adv_qty:
                qty = max_adv_qty
                decision = RiskDecision.SCALE
                reasons.append("ADV liquidity cap")

        max_position_pct = float(self.config.get("max_position_pct", 0.10))
        max_position_value = ctx.portfolio_value * max_position_pct
        current_qty = int(ctx.positions.get(order.symbol, {}).get("qty", 0))
        if order.side.upper() == "BUY":
            max_total_qty = int(max_position_value // order.limit_price)
            allowed_by_position = max(0, max_total_qty - max(current_qty, 0))
            if allowed_by_position <= 0:
                return RiskDecision.REJECT, 0, "position cap reached"
            if qty > allowed_by_position:
                qty = allowed_by_position
                decision = RiskDecision.SCALE
                reasons.append("10% position cap")

        max_notional = float(self.config.get("max_order_notional_inr", float("inf")))
        if qty * order.limit_price > max_notional:
            return RiskDecision.REJECT, 0, "max notional exceeded"

        if order.side.upper() == "BUY":
            fee_buffer = float(self.config.get("fee_buffer_pct", 0.001))
            affordable_qty = int(ctx.cash // (order.limit_price * (1 + fee_buffer)))
            if affordable_qty <= 0:
                return RiskDecision.REJECT, 0, "insufficient cash"
            if affordable_qty < qty:
                qty = affordable_qty
                decision = RiskDecision.SCALE
                reasons.append("insufficient cash")

        if qty <= 0:
            return RiskDecision.REJECT, 0, "no quantity allowed"
        if decision is RiskDecision.SCALE:
            return decision, qty, ", ".join(reasons)
        return RiskDecision.ALLOW, qty, "allowed"
