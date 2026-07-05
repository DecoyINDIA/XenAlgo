from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconcileResult:
    clean: bool
    should_halt: bool
    drift: dict[str, tuple[int, int]]


class Reconciler:
    def __init__(self, broker) -> None:
        self.broker = broker

    def broker_truth_positions(self) -> dict[str, int]:
        truth: dict[str, int] = {}
        for holding in self.broker.get_holdings():
            symbol = holding.get("tradingSymbol") or holding.get("symbol")
            qty = int(holding.get("totalQty", holding.get("qty", 0)))
            if symbol:
                truth[symbol] = truth.get(symbol, 0) + qty
        for position in self.broker.get_positions():
            symbol = position.get("tradingSymbol") or position.get("symbol")
            qty = int(position.get("netQty", position.get("qty", 0)))
            if symbol and qty:
                truth[symbol] = truth.get(symbol, 0) + qty
        return truth

    def reconcile(self, local: dict[str, int]) -> ReconcileResult:
        truth = self.broker_truth_positions()
        symbols = set(local) | set(truth)
        drift = {
            symbol: (int(local.get(symbol, 0)), int(truth.get(symbol, 0)))
            for symbol in symbols
            if int(local.get(symbol, 0)) != int(truth.get(symbol, 0))
        }
        return ReconcileResult(clean=not drift, should_halt=bool(drift), drift=drift)

    def portfolio_value(self, ltp: dict[str, float]) -> float:
        funds = self.broker.get_funds()
        cash = float(funds.get("availabelBalance", funds.get("availableBalance", 0.0)))
        holdings_value = sum(
            qty * float(ltp.get(symbol, 0.0))
            for symbol, qty in self.broker_truth_positions().items()
        )
        return cash + holdings_value
