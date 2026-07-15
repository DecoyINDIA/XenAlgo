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
        security_id = getattr(req, "security_id", "")
        self._orders[cid] = {
            "broker_order_id": oid,
            "state": "PENDING",
            "symbol": symbol,
            "security_id": security_id,
            "side": side,
            "requested_qty": qty,
            "limit_price": price,
            "filled_qty": 0,
            "avg_price": 0.0,
        }
        if side == "BUY" and self.cash < qty * price:
            self._orders[cid]["state"] = "REJECTED"
            return PaperAck("REJECTED", oid, cid, "insufficient paper cash")
        if side == "SELL" and self.holdings.get(symbol, 0) < qty:
            self._orders[cid]["state"] = "REJECTED"
            return PaperAck("REJECTED", oid, cid, "insufficient paper holdings")
        return PaperAck("PENDING", oid, cid)

    def modify_order(
        self,
        broker_order_id: str,
        *,
        qty: int | None = None,
        limit_price: float | None = None,
    ) -> PaperAck:
        order, cid = self._find_order(broker_order_id)
        if order["state"] != "PENDING":
            return PaperAck(
                "REJECTED",
                broker_order_id,
                cid,
                f"cannot modify {order['state']} order",
            )
        if qty is not None:
            order["requested_qty"] = int(qty)
        if limit_price is not None:
            order["limit_price"] = float(limit_price)
        return PaperAck("PENDING", broker_order_id, cid)

    def cancel_order(self, broker_order_id: str) -> PaperAck:
        order, cid = self._find_order(broker_order_id)
        if order["state"] in {"TRADED", "REJECTED", "CANCELLED"}:
            return PaperAck("REJECTED", broker_order_id, cid, f"cannot cancel {order['state']} order")
        order["state"] = "CANCELLED"
        return PaperAck("CANCELLED", broker_order_id, cid)

    def mark_filled(self, correlation_id: str) -> None:
        order = self._orders[correlation_id]
        if order["state"] != "PENDING":
            return
        qty = int(order.get("requested_qty", 0) or order.get("filled_qty", 0) or 0)
        if qty <= 0:
            qty = 1
        price = self.ltp.get(order["symbol"])
        if price is None:
            price = order.get("avg_price")
        if price is None or float(price) <= 0.0:
            order.update(state="REJECTED", reason="no paper mark price")
            return
        price = float(price)
        side = order["side"]
        sign = 1 if side == "BUY" else -1
        self.holdings[order["symbol"]] = self.holdings.get(order["symbol"], 0) + sign * qty
        self.cash -= sign * qty * price
        order.update(state="TRADED", filled_qty=qty, avg_price=price)

    def get_order_by_correlation(self, cid: str):
        return self._orders.get(cid)

    def get_order_by_id(self, broker_order_id: str):
        try:
            order, _ = self._find_order(broker_order_id)
        except KeyError:
            return None
        return order

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

    def _find_order(self, broker_order_id: str) -> tuple[dict, str]:
        for cid, order in self._orders.items():
            if order["broker_order_id"] == broker_order_id:
                return order, cid
        raise KeyError(f"unknown paper order id: {broker_order_id}")
