from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from xenalgo.execution import Fill, FillListener
from xenalgo.risk import OrderRequest


@dataclass(frozen=True)
class FyersAck:
    status: str
    broker_order_id: str | None
    correlation_id: str
    reason: str = ""


class FyersSymbolResolver:
    """Resolve NSE cash symbols to Fyers v3 symbol strings."""

    def __init__(self, symbol_master: dict[str, str] | None = None) -> None:
        self.symbol_master = {k.upper(): v for k, v in (symbol_master or {}).items()}

    def resolve(self, symbol: str) -> str:
        clean = symbol.upper().strip()
        return self.symbol_master.get(clean, f"NSE:{clean}-EQ")


class FyersGateway:
    """Mockable Fyers REST gateway behind the existing broker contract.

    The concrete SDK client is injected. Tests pass a fake object; live code can pass
    fyers_apiv3.fyersModel.FyersModel after the operator enables the live boundary.
    """

    def __init__(
        self,
        client: Any,
        *,
        symbol_resolver: FyersSymbolResolver | None = None,
        order_type: str = "MARKETABLE_LIMIT",
        product_type: str = "CNC",
    ) -> None:
        self.client = client
        self.symbol_resolver = symbol_resolver or FyersSymbolResolver()
        self.order_type = order_type
        self.product_type = product_type
        self._orders_by_tag: dict[str, dict[str, Any]] = {}

    def place_order(self, req: OrderRequest) -> FyersAck:
        existing = self.get_order_by_correlation(req.correlation_id)
        if existing:
            return FyersAck("DUPLICATE", _order_id(existing), req.correlation_id)

        payload = self._payload(req)
        response = self.client.place_order(payload)
        order_id = _response_order_id(response)
        ok = _response_ok(response)
        status = "PENDING" if ok else "REJECTED"
        reason = "" if ok else str(response.get("message") or response.get("s") or "Fyers rejected order")
        self._orders_by_tag[req.correlation_id] = {
            **payload,
            "id": order_id,
            "status": status,
            "filledQty": 0,
            "message": reason,
        }
        return FyersAck(status, order_id, req.correlation_id, reason)

    def cancel_order(self, broker_order_id: str) -> FyersAck:
        response = self.client.cancel_order({"id": broker_order_id})
        status = "CANCELLED" if _response_ok(response) else "REJECTED"
        return FyersAck(status, broker_order_id, "", str(response.get("message", "")))

    def modify_order(
        self,
        broker_order_id: str,
        *,
        qty: int | None = None,
        limit_price: float | None = None,
    ) -> FyersAck:
        payload: dict[str, Any] = {"id": broker_order_id}
        if qty is not None:
            payload["qty"] = int(qty)
        if limit_price is not None:
            payload["limitPrice"] = float(limit_price)
        response = self.client.modify_order(payload)
        status = "PENDING" if _response_ok(response) else "REJECTED"
        return FyersAck(status, broker_order_id, "", str(response.get("message", "")))

    def get_order_by_correlation(self, cid: str) -> dict[str, Any] | None:
        order = None
        if cid in self._orders_by_tag:
            order = self._orders_by_tag[cid]
        else:
            for o in self.get_orderbook():
                if str(o.get("tag") or o.get("orderTag") or "") == cid:
                    self._orders_by_tag[cid] = o
                    order = o
                    break
        if order is not None:
            order_copy = dict(order)
            raw_status = order.get("status") or order.get("orderStatus") or order.get("statusText")
            order_copy["state"] = normalize_fyers_state(raw_status)
            order_copy["broker_order_id"] = _order_id(order)
            return order_copy
        return None

    def get_orderbook(self) -> list[dict[str, Any]]:
        response = self.client.orderbook()
        if isinstance(response, dict):
            orders = response.get("orderBook") or response.get("data") or []
            return list(orders) if isinstance(orders, list) else []
        return []

    def get_holdings(self):
        return self.client.holdings()

    def get_positions(self):
        return self.client.positions()

    def get_funds(self):
        return self.client.funds()

    def _payload(self, req: OrderRequest) -> dict[str, Any]:
        is_market = self.order_type.upper() == "MARKET"
        return {
            "symbol": self.symbol_resolver.resolve(req.symbol),
            "qty": int(req.qty),
            "type": 2 if is_market else 1,
            "side": 1 if req.side.upper() == "BUY" else -1,
            "productType": self.product_type,
            "limitPrice": 0 if is_market else float(req.limit_price),
            "stopPrice": 0,
            "validity": "DAY",
            "offlineOrder": False,
            "tag": req.correlation_id,
        }


class FyersOrderFillConsumer:
    """Convert Fyers OrderSocket/orderbook payloads into idempotent fills."""

    def __init__(self, listener: FillListener) -> None:
        self.listener = listener

    def on_trade(self, payload: dict[str, Any]) -> None:
        fill = fyers_payload_to_fill(payload)
        if fill is not None:
            self.listener.on_fill(fill)

    def poll_orderbook(self, orders: Iterable[dict[str, Any]]) -> None:
        for order in orders:
            fill = fyers_payload_to_fill(order)
            if fill is not None:
                self.listener.on_fill(fill)


class FyersOrderStreamAdapter:
    """Supervised, injected Order WebSocket boundary with explicit health state."""

    def __init__(self, socket_factory: Callable[..., Any], consumer: FyersOrderFillConsumer) -> None:
        self.socket_factory = socket_factory
        self.consumer = consumer
        self.socket: Any | None = None
        self.connected = False
        self.last_message_at: dt.datetime | None = None
        self.reconnects = 0
        self.last_error = ""

    def start(self) -> None:
        try:
            self.socket = self.socket_factory(
                on_orders=self.on_message,
                on_trades=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
            )
            self.socket.connect()
            self.connected = True
        except Exception as exc:
            self.connected = False
            self.last_error = type(exc).__name__
            raise

    def stop(self) -> None:
        if self.socket is not None and hasattr(self.socket, "close_connection"):
            self.socket.close_connection()
        self.connected = False

    def reconnect(self) -> None:
        self.stop()
        self.reconnects += 1
        self.start()

    def on_message(self, payload: dict[str, Any]) -> None:
        self.last_message_at = dt.datetime.now(dt.UTC)
        self.consumer.on_trade(payload)

    def on_error(self, error: Any) -> None:
        self.connected = False
        self.last_error = type(error).__name__ if isinstance(error, BaseException) else "stream_error"

    def on_close(self, *_args: Any) -> None:
        self.connected = False

    def health(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "last_message_at": None if self.last_message_at is None else self.last_message_at.isoformat(),
            "reconnects": self.reconnects,
            "last_error": self.last_error,
        }


class FyersOrderbookPoller:
    """REST recovery channel converging through the same fill consumer."""

    def __init__(self, gateway: FyersGateway, consumer: FyersOrderFillConsumer) -> None:
        self.gateway = gateway
        self.consumer = consumer
        self.last_poll_at: dt.datetime | None = None
        self.last_error = ""

    def poll(self) -> list[dict[str, Any]]:
        try:
            orders = self.gateway.get_orderbook()
            self.consumer.poll_orderbook(orders)
            self.last_poll_at = dt.datetime.now(dt.UTC)
            self.last_error = ""
            return orders
        except Exception as exc:
            self.last_error = type(exc).__name__
            raise

    def health(self) -> dict[str, Any]:
        return {
            "last_poll_at": None if self.last_poll_at is None else self.last_poll_at.isoformat(),
            "last_error": self.last_error,
        }


def normalize_fyers_state(status_val: Any) -> str:
    s = str(status_val).upper().strip()
    if s in {"2", "TRADED", "FILLED", "COMPLETE", "COMPLETED"}:
        return "TRADED"
    if s in {"5", "REJECTED"}:
        return "REJECTED"
    if s in {"1", "CANCELLED", "CANCELED"}:
        return "CANCELLED"
    if s in {"6", "PENDING"}:
        return "PENDING"
    if s in {"PART_TRADED", "PARTIALLY_FILLED"}:
        return "PART_TRADED"
    return "PENDING"


def fyers_payload_to_fill(payload: dict[str, Any]) -> Fill | None:
    cumulative_qty = _first_int(payload, "filledQty", "tradedQty", "filled_qty", "qtyTraded")
    if cumulative_qty <= 0:
        return None
    cid = str(
        payload.get("tag")
        or payload.get("orderTag")
        or payload.get("correlation_id")
        or payload.get("correlationId")
        or ""
    )
    if not cid:
        return None
    broker_order_id = _order_id(payload)
    status = str(payload.get("status") or payload.get("orderStatus") or payload.get("statusText") or "TRADED")
    state = "TRADED" if _is_terminal_trade(status, payload) else "PART_TRADED"
    symbol = str(payload.get("symbol") or payload.get("tradingSymbol") or "").split(":")[-1].removesuffix("-EQ")
    side = _side(payload)
    price = float(
        payload.get("avgTradePrice")
        or payload.get("tradedPrice")
        or payload.get("averageTradedPrice")
        or payload.get("limitPrice")
        or 0.0
    )
    if price <= 0.0:
        return None
    event_key = f"fyers:{broker_order_id or cid}:{state}:{cumulative_qty}"
    return Fill(
        correlation_id=cid,
        broker_order_id=broker_order_id,
        symbol=symbol,
        side=side,
        filled_qty=cumulative_qty,
        avg_price=price,
        event_key=event_key,
        state=state,
    )


def _response_ok(response: dict[str, Any]) -> bool:
    return response.get("s") == "ok" or response.get("code") in {1101, 200} or response.get("status") in {"ok", "success"}


def _response_order_id(response: dict[str, Any]) -> str | None:
    value = response.get("id") or response.get("order_id")
    if value:
        return str(value)
    data = response.get("data")
    if isinstance(data, dict):
        return _order_id(data)
    return None


def _order_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("orderId") or payload.get("order_id")
    return None if value in {None, ""} else str(value)


def _first_int(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return int(payload[key])
    return 0


def _is_terminal_trade(status: str, payload: dict[str, Any]) -> bool:
    normalized = status.upper()
    if normalized in {"TRADED", "FILLED", "COMPLETE", "COMPLETED"}:
        return True
    filled = _first_int(payload, "filledQty", "tradedQty", "filled_qty", "qtyTraded")
    qty = _first_int(payload, "qty", "quantity")
    return qty > 0 and filled >= qty


def _side(payload: dict[str, Any]) -> str:
    side = payload.get("side") or payload.get("transactionType") or payload.get("type")
    if str(side).upper() in {"-1", "SELL"}:
        return "SELL"
    return "BUY"


def default_fyers_history_chunks(start: dt.date, end: dt.date, max_days: int = 365) -> list[tuple[dt.date, dt.date]]:
    chunks: list[tuple[dt.date, dt.date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + dt.timedelta(days=max_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + dt.timedelta(days=1)
    return chunks
