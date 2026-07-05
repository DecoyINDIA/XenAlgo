from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from xenalgo import data
from xenalgo.alerts import InMemoryAlerter
from xenalgo.broker.paper import PaperBroker
from xenalgo.broker.token import TokenManager
from xenalgo.execution import ExecutionEngine, Fill, FillListener, Journal
from xenalgo.execution.reconcile import Reconciler
from xenalgo.risk import RiskContext, RiskEngine


@dataclass(frozen=True)
class PaperOrderPlan:
    correlation_id: str
    sleeve: str
    symbol: str
    security_id: str
    side: str
    qty: int
    limit_price: float


@dataclass(frozen=True)
class PaperDayResult:
    submitted: int
    filled: int
    reconciled: bool
    alerts: int


class PaperDayRunner:
    """Phase 1 paper-mode orchestration: token -> data -> risk -> order -> fill -> reconcile."""

    def __init__(
        self,
        broker: PaperBroker,
        journal: Journal,
        token_manager: TokenManager,
        risk_engine: RiskEngine,
        alerter: InMemoryAlerter | None = None,
    ) -> None:
        self.broker = broker
        self.journal = journal
        self.token_manager = token_manager
        self.risk_engine = risk_engine
        self.alerter = alerter or InMemoryAlerter()

    def run(
        self,
        *,
        panel: dict,
        expected_trading_date: str | dt.date,
        orders: list[PaperOrderPlan],
    ) -> PaperDayResult:
        self.token_manager.ensure_valid()
        data.assert_panel_fresh(panel, expected_trading_date)
        data.assert_latest_prices_sane(panel, self.risk_engine.config.get("price_collar_pct", 0.03))

        close = panel["close"]
        prev_close = {symbol: float(close[symbol].iloc[-1]) for symbol in close.columns}
        adv = {}
        if "volume" in panel:
            volume = panel["volume"]
            adv = {symbol: float(volume[symbol].iloc[-1]) for symbol in volume.columns}

        submitted = 0
        filled = 0
        listener = FillListener(self.broker, self.journal)

        for plan in orders:
            ctx = RiskContext(
                portfolio_value=Reconciler(self.broker).portfolio_value(prev_close),
                positions={},
                adv=adv,
                prev_close=prev_close,
                cash=self.broker.cash,
                restricted=set(),
                seen_correlation_ids=set(),
                breakers={},
            )
            engine = ExecutionEngine(
                self.broker,
                self.journal,
                risk_engine=self.risk_engine,
                risk_context=ctx,
            )
            result = engine.submit(**plan.__dict__)
            self.alerter.send("order", f"{plan.correlation_id} {result.state}")
            if result.state != "PENDING":
                continue
            submitted += 1
            order = self.broker.get_order_by_correlation(plan.correlation_id)
            order["requested_qty"] = plan.qty
            self.broker.mark_filled(plan.correlation_id)
            filled_order = self.broker.get_order_by_correlation(plan.correlation_id)
            listener.on_fill(
                Fill(
                    correlation_id=plan.correlation_id,
                    symbol=plan.symbol,
                    side=plan.side,
                    filled_qty=int(filled_order["filled_qty"]),
                    avg_price=float(filled_order["avg_price"]),
                    broker_order_id=filled_order["broker_order_id"],
                    event_key=f"{filled_order['broker_order_id']}:TRADED",
                )
            )
            self.alerter.send("fill", f"{plan.correlation_id} filled")
            filled += 1

        local = {symbol: listener.book.qty(symbol) for symbol in self.broker.holdings}
        reconciled = Reconciler(self.broker).reconcile(local).clean
        self.alerter.send("reconcile", "clean" if reconciled else "drift", critical=not reconciled)
        return PaperDayResult(submitted, filled, reconciled, len(self.alerter.sent))
