from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol


@dataclass(frozen=True)
class BrokerAck:
    status: str
    broker_order_id: str | None
    correlation_id: str
    reason: str = ""


class AuthProvider(Protocol):
    """Daily-session auth boundary; implementations must never log credentials or tokens."""

    def __call__(self): ...


class MarketDataProvider(Protocol):
    def history(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def quotes(self, symbols: Iterable[str]) -> dict[str, float]: ...


class OrderGateway(Protocol):
    """Broker-neutral order boundary used only behind ExecutionEngine."""

    def place_order(self, request: Any) -> BrokerAck: ...

    def modify_order(
        self, broker_order_id: str, *, qty: int | None = None, limit_price: float | None = None
    ) -> BrokerAck: ...

    def cancel_order(self, broker_order_id: str) -> BrokerAck: ...

    def get_order_by_correlation(self, correlation_id: str) -> dict[str, Any] | None: ...

    def get_holdings(self): ...

    def get_positions(self): ...

    def get_funds(self): ...


class FillStream(Protocol):
    def start(self, on_message: Callable[[dict[str, Any]], None]) -> None: ...

    def stop(self) -> None: ...

    def health(self) -> dict[str, Any]: ...


class OrderbookPoller(Protocol):
    def poll(self) -> Iterable[dict[str, Any]]: ...
