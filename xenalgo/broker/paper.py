from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperAck:
    status: str
    broker_order_id: str | None
    correlation_id: str
    reason: str = ""


class PaperBroker:
    """In-memory BrokerInterface implementation for Phase 1 paper mode."""

    def __init__(self, cash: float = 10_000_000.0, ltp: dict[str, float] | None = None) -> None:
        self.cash = float(cash)
        self.ltp = dict(ltp or {})
        self.holdings: dict[str, int] = {}
        self.positions: dict[str, int] = {}
        self._orders: dict[str, dict] = {}
        self._seq = 0

    def place_order(self, req) -> PaperAck:
        cid = getattr(req, "correlation_id")
        if cid in self._orders:
            order = self._orders[cid]
            return PaperAck("DUPLICATE", order["broker_order_id"], cid)

        self._seq += 1
        oid = f"paper-{self._seq}"
        qty = int(getattr(req, "qty"))
        price = float(getattr(req, "limit_price"))
        side = getattr(req, "side").upper()
        symbol = getattr(req, "symbol")
        self._orders[cid] = {
            "broker_order_id": oid,
            "state": "PENDING",
            "symbol": symbol,
            "side": side,
            "filled_qty": 0,
            "avg_price": 0.0,
        }
        if side == "BUY" and self.cash < qty * price:
            self._orders[cid]["state"] = "REJECTED"
            return PaperAck("REJECTED", oid, cid, "insufficient paper cash")
        return PaperAck("PENDING", oid, cid)

    def mark_filled(self, correlation_id: str) -> None:
        order = self._orders[correlation_id]
        if order["state"] == "TRADED":
            return
        qty = int(order.get("requested_qty", 0) or order.get("filled_qty", 0) or 0)
        if qty <= 0:
            qty = 1
        price = float(self.ltp.get(order["symbol"], order.get("avg_price") or 0.0))
        side = order["side"]
        sign = 1 if side == "BUY" else -1
        self.holdings[order["symbol"]] = self.holdings.get(order["symbol"], 0) + sign * qty
        self.cash -= sign * qty * price
        order.update(state="TRADED", filled_qty=qty, avg_price=price)

    def get_order_by_correlation(self, cid: str):
        return self._orders.get(cid)

    def get_holdings(self):
        return [
            {"tradingSymbol": symbol, "totalQty": qty}
            for symbol, qty in self.holdings.items()
            if qty
        ]

    def get_positions(self):
        return [
            {"tradingSymbol": symbol, "netQty": qty}
            for symbol, qty in self.positions.items()
            if qty
        ]

    def get_funds(self):
        return {"availabelBalance": self.cash}
