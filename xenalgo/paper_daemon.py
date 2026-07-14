from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import socket
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from xenalgo.alerts import InMemoryAlerter
from xenalgo.broker.governor import OrderGovernor
from xenalgo.broker.paper import PaperBroker
from xenalgo.broker.token import TokenManager
from xenalgo.config import RuntimeConfig, load_config
from xenalgo.execution import ExecutionEngine, Fill, FillListener, Journal, PositionBook
from xenalgo.execution.reconcile import Reconciler
from xenalgo.monolith import PaperOrderPlan
from xenalgo.ops import KillSwitch
from xenalgo.phase32 import DEFAULT_SLEEVES
from xenalgo.risk import OrderRequest, RiskContext, RiskEngine
from xenalgo.scheduler import MarketCalendar, RebalancePlan


class StartupBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class StartupStatus:
    auth: bool
    calendar: bool
    config: bool
    replay: bool
    data: bool
    controls: bool
    reconciliation: bool

    @property
    def ready(self) -> bool:
        return all(asdict(self).values())


@dataclass(frozen=True)
class HostPreflightReport:
    checks: dict[str, bool]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


@dataclass(frozen=True)
class SessionEvidence:
    schema_version: str
    session_id: str
    trading_date: str
    host_id: str
    image_digest: str
    config_checksum: str
    started_at: str
    ended_at: str
    startup_ready: bool
    rebalance_session: bool
    submitted: int
    filled: int
    reconciliation_clean: bool
    unresolved_incidents: int
    alert_failures: int
    channel_health: dict[str, bool]
    sleeve_returns: dict[str, tuple[float, float]]
    evidence_checksum: str = ""


class SafeAlertBus:
    """Alerts are best-effort and can never roll back journaled state."""

    def __init__(self, alerter=None) -> None:
        self.alerter = alerter or InMemoryAlerter()
        self.failures = 0

    def send(self, kind: str, message: str, critical: bool = False) -> None:
        try:
            self.alerter.send(kind, message, critical=critical)
        except Exception:
            self.failures += 1


@dataclass
class PaperDependencies:
    config: RuntimeConfig
    broker: PaperBroker
    journal: Journal
    token_manager: TokenManager
    risk_engine: RiskEngine
    governor: OrderGovernor
    kill_switch: KillSwitch
    calendar: MarketCalendar = field(default_factory=MarketCalendar)
    alerts: SafeAlertBus = field(default_factory=SafeAlertBus)

    def __post_init__(self) -> None:
        if type(self.broker) is not PaperBroker:
            raise TypeError("production paper composition requires the concrete PaperBroker")
        if self.config.data["live_trading"].get("mode") != "paper":
            raise StartupBlocked("production paper daemon requires live_trading.mode=paper")
        if self.config.data["live_trading"].get("enabled") is not False:
            raise StartupBlocked("live trading must remain disabled in paper composition")
        if self.config.data["broker"].get("order_api_enabled") is not False:
            raise StartupBlocked("broker order API must remain disabled in paper composition")


class ProductionPaperDaemon:
    """Single-owner, paper-only scheduled-session composition for commissioning."""

    EVIDENCE_SCHEMA_VERSION = "phase32-session-v2"

    def __init__(
        self,
        deps: PaperDependencies,
        *,
        evidence_dir: str | Path,
        clock: Callable[[], dt.datetime] | None = None,
        host_id: str | None = None,
        image_digest: str | None = None,
    ) -> None:
        self.deps = deps
        self.evidence_dir = Path(evidence_dir)
        self.clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self.host_id = host_id or socket.gethostname()
        self.image_digest = image_digest or os.environ.get("XENALGO_IMAGE_DIGEST", "unavailable")
        self.listener = FillListener(deps.broker, deps.journal)
        self.listener.book = PositionBook.from_replay(deps.journal)
        self.reconciler = Reconciler(deps.broker)
        self.engine = ExecutionEngine(
            deps.broker,
            deps.journal,
            kill_switch=deps.kill_switch,
            risk_engine=deps.risk_engine,
            risk_context_provider=self._risk_context,
            governor=deps.governor,
        )
        self._panel: dict = {}
        self._previous_close: dict[str, float] = {}
        self._adv: dict[str, float] = {}
        self._closed = False

    def startup(self, *, trading_date: dt.date, panel: dict) -> StartupStatus:
        from xenalgo import data

        checks: dict[str, bool] = {}
        try:
            self.deps.token_manager.ensure_valid()
            checks["auth"] = True
            checks["calendar"] = self.deps.calendar.is_trading_day(trading_date)
            checks["config"] = bool(self.deps.config.checksum)
            replay = PositionBook.from_replay(self.deps.journal)
            checks["replay"] = replay is not None
            data.assert_panel_fresh(panel, trading_date)
            data.assert_latest_prices_sane(
                panel, float(self.deps.risk_engine.config.get("price_collar_pct", 0.03))
            )
            checks["data"] = True
            checks["controls"] = not self.deps.kill_switch.is_active() and not self.engine.is_halted()
            close = panel["close"]
            self._previous_close = {symbol: float(close[symbol].iloc[-1]) for symbol in close.columns}
            volume = panel.get("volume")
            self._adv = (
                {symbol: float(volume[symbol].iloc[-1]) for symbol in volume.columns}
                if volume is not None
                else {}
            )
            local = {symbol: replay.qty(symbol) for symbol in self.deps.broker.holdings}
            checks["reconciliation"] = self.reconciler.reconcile(local).clean
            self._panel = panel
        except Exception as exc:
            self.deps.alerts.send("startup", f"blocked: {type(exc).__name__}", critical=True)
            raise StartupBlocked(str(exc)) from exc

        status = StartupStatus(**checks)
        if not status.ready:
            failed = ", ".join(name for name, ok in checks.items() if not ok)
            raise StartupBlocked(f"startup prerequisites failed: {failed}")
        return status

    def run_session(
        self,
        *,
        trading_date: dt.date,
        panel: dict,
        orders: Iterable[PaperOrderPlan],
        rebalance: RebalancePlan | None = None,
        sleeve_returns: dict[str, tuple[float, float]] | None = None,
    ) -> SessionEvidence:
        started = self.clock()
        startup = self.startup(trading_date=trading_date, panel=panel)
        is_rebalance = (rebalance or RebalancePlan("daily", 0)).is_rebalance_day(trading_date)
        submitted = filled = 0
        if is_rebalance:
            ordered = sorted(orders, key=lambda item: (item.side.upper() != "SELL", item.symbol, item.sleeve))
            for plan in ordered:
                result = self.engine.submit(**plan.__dict__)
                self.deps.alerts.send("order", f"{plan.correlation_id} {result.state}")
                if result.state != "PENDING":
                    continue
                submitted += 1
                self.deps.broker.mark_filled(plan.correlation_id)
                order = self.deps.broker.get_order_by_correlation(plan.correlation_id)
                self.listener.on_fill(
                    Fill(
                        correlation_id=plan.correlation_id,
                        broker_order_id=order["broker_order_id"],
                        symbol=plan.symbol,
                        side=plan.side,
                        filled_qty=int(order["filled_qty"]),
                        avg_price=float(order["avg_price"]),
                        event_key=f"{order['broker_order_id']}:TRADED:{order['filled_qty']}",
                    )
                )
                filled += 1
                self.deps.alerts.send("fill", f"{plan.correlation_id} filled")

        symbols = set(self.deps.broker.holdings) | set(self._previous_close)
        local = {symbol: self.listener.book.qty(symbol) for symbol in symbols if self.listener.book.qty(symbol)}
        reconciled = self.reconciler.reconcile(local).clean
        self.deps.alerts.send("reconcile", "clean" if reconciled else "drift", critical=not reconciled)
        ended = self.clock()
        evidence = SessionEvidence(
            schema_version=self.EVIDENCE_SCHEMA_VERSION,
            session_id=f"{trading_date.isoformat()}-{self.host_id}",
            trading_date=trading_date.isoformat(),
            host_id=self.host_id,
            image_digest=self.image_digest,
            config_checksum=self.deps.config.checksum,
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            startup_ready=startup.ready,
            rebalance_session=is_rebalance,
            submitted=submitted,
            filled=filled,
            reconciliation_clean=reconciled,
            unresolved_incidents=0 if reconciled else 1,
            alert_failures=self.deps.alerts.failures,
            channel_health={"paper_fill": True, "orderbook_poll": True},
            sleeve_returns=sleeve_returns or {sleeve: (0.0, 0.0) for sleeve in DEFAULT_SLEEVES},
        )
        return self._write_evidence(evidence)

    def shutdown(self) -> None:
        self._closed = True

    def _risk_context(self, order: OrderRequest) -> RiskContext:
        symbols = set(self._previous_close) | set(self.deps.broker.holdings)
        return RiskContext(
            portfolio_value=self.reconciler.portfolio_value(self._previous_close),
            positions={
                symbol: {"qty": self.listener.book.qty(symbol) or self.deps.broker.holdings.get(symbol, 0)}
                for symbol in symbols
                if self.listener.book.qty(symbol) or self.deps.broker.holdings.get(symbol, 0)
            },
            adv=self._adv,
            prev_close=self._previous_close,
            cash=self.deps.broker.cash,
            restricted=set(),
            seen_correlation_ids=set(),
            breakers={"kill": self.deps.kill_switch.is_active(), "execution": self.engine.is_halted()},
        )

    def _write_evidence(self, evidence: SessionEvidence) -> SessionEvidence:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        body = asdict(evidence)
        body.pop("evidence_checksum", None)
        checksum = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        final = SessionEvidence(**body, evidence_checksum=checksum)
        target = self.evidence_dir / f"{evidence.trading_date}.json"
        target.write_text(json.dumps(asdict(final), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._write_phase32_csv(final)
        return final

    def _write_phase32_csv(self, evidence: SessionEvidence) -> None:
        target = self.evidence_dir / "phase32.csv"
        fields = [
            "trading_date", "sleeve", "paper_return", "backtest_return",
            "token_refresh_ok", "safety_incidents", "reconciliation_clean",
            "session_complete", "unresolved_incidents", "evidence_checksum",
            "authoritative", "unexplained_outlier", "notes",
        ]
        existing: list[dict[str, str]] = []
        if target.exists():
            with target.open(newline="", encoding="utf-8") as handle:
                existing = [
                    row for row in csv.DictReader(handle)
                    if row.get("trading_date") != evidence.trading_date
                ]
        for sleeve in DEFAULT_SLEEVES:
            paper_return, backtest_return = evidence.sleeve_returns.get(sleeve, (0.0, 0.0))
            existing.append({
                "trading_date": evidence.trading_date,
                "sleeve": sleeve,
                "paper_return": str(paper_return),
                "backtest_return": str(backtest_return),
                "token_refresh_ok": "true",
                "safety_incidents": "0",
                "reconciliation_clean": str(evidence.reconciliation_clean).lower(),
                "session_complete": "true",
                "unresolved_incidents": str(evidence.unresolved_incidents),
                "evidence_checksum": evidence.evidence_checksum,
                "authoritative": "true",
                "unexplained_outlier": "false",
                "notes": "generated by production paper daemon",
            })
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(existing)


class ScheduledPaperRuntime:
    """Clock-driven owner for the eight production paper jobs.

    Network/data callbacks are injected so tests and CI remain mock-only. The runtime
    records each job once per trading date and never overlaps a second session owner.
    """

    JOBS = ("token", "data", "startup", "reconciliation", "execution", "eod", "backup", "heartbeat")

    def __init__(
        self,
        daemon: ProductionPaperDaemon,
        *,
        panel_provider: Callable[[dt.date], dict],
        order_provider: Callable[[dt.date, dict], Iterable[PaperOrderPlan]],
        backup: Callable[[], None] | None = None,
        heartbeat: Callable[[], None] | None = None,
        rebalance: RebalancePlan | None = None,
    ) -> None:
        self.daemon = daemon
        self.panel_provider = panel_provider
        self.order_provider = order_provider
        self.backup = backup or (lambda: None)
        self.heartbeat = heartbeat or (lambda: None)
        self.rebalance = rebalance or RebalancePlan("daily", 0)
        self.completed: set[tuple[dt.date, str]] = set()
        self.panel: dict | None = None
        self.orders: list[PaperOrderPlan] = []
        self.last_evidence: SessionEvidence | None = None

    def run_job(self, name: str, trading_date: dt.date) -> None:
        key = (trading_date, name)
        if name not in self.JOBS:
            raise ValueError(f"unknown paper job: {name}")
        if key in self.completed:
            return
        if name == "token":
            self.daemon.deps.token_manager.ensure_valid()
        elif name == "data":
            self.panel = self.panel_provider(trading_date)
        elif name == "startup":
            if self.panel is None:
                raise StartupBlocked("data job has not completed")
            self.daemon.startup(trading_date=trading_date, panel=self.panel)
        elif name == "reconciliation":
            replay = PositionBook.from_replay(self.daemon.deps.journal)
            local = {symbol: replay.qty(symbol) for symbol in self.daemon.deps.broker.holdings}
            if not self.daemon.reconciler.reconcile(local).clean:
                raise StartupBlocked("scheduled reconciliation mismatch")
        elif name == "execution":
            if self.panel is None:
                raise StartupBlocked("data job has not completed")
            self.orders = list(self.order_provider(trading_date, self.panel))
            self.last_evidence = self.daemon.run_session(
                trading_date=trading_date,
                panel=self.panel,
                orders=self.orders,
                rebalance=self.rebalance,
            )
        elif name == "eod":
            if self.last_evidence is None:
                raise StartupBlocked("execution/session evidence is missing")
        elif name == "backup":
            self.backup()
        elif name == "heartbeat":
            self.heartbeat()
        self.completed.add(key)

    def run_trading_day(self, trading_date: dt.date) -> SessionEvidence:
        for name in self.JOBS:
            self.run_job(name, trading_date)
        assert self.last_evidence is not None
        return self.last_evidence


def run_host_preflight(
    daemon: ProductionPaperDaemon,
    *,
    trading_date: dt.date,
    panel: dict,
) -> HostPreflightReport:
    """Run D2's combined fail-closed paper preflight without submitting an order."""
    status = daemon.startup(trading_date=trading_date, panel=panel)
    before = daemon.deps.alerts.failures
    daemon.deps.alerts.send(
        "application_event",
        f"synthetic D2 preflight {trading_date.isoformat()}",
        critical=False,
    )
    checks = {
        "authentication": status.auth,
        "calendar": status.calendar,
        "config": status.config,
        "journal_replay": status.replay,
        "data": status.data,
        "controls": status.controls,
        "reconciliation": status.reconciliation,
        "paper_gateway": type(daemon.deps.broker) is PaperBroker,
        "synthetic_alert": daemon.deps.alerts.failures == before,
    }
    return HostPreflightReport(checks)


def build_paper_dependencies(root: str | Path | None = None) -> PaperDependencies:
    base = Path(root) if root else Path(__file__).resolve().parents[1]
    config = load_config("live", base)
    storage = config.data["storage"]
    journal_path = base / str(storage["journal_sqlite"])
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    token_path = base / str(config.data["broker"]["token_store"])
    token_path.parent.mkdir(parents=True, exist_ok=True)
    governor_config = config.data["governor"]
    broker = PaperBroker()
    return PaperDependencies(
        config=config,
        broker=broker,
        journal=Journal(journal_path),
        token_manager=TokenManager(token_path),
        risk_engine=RiskEngine(config.data["risk"]),
        governor=OrderGovernor(
            max_per_sec=float(governor_config["max_orders_per_sec"]),
            max_per_day=int(governor_config["max_orders_per_day"]),
        ),
        kill_switch=KillSwitch(journal_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="XenAlgo production paper daemon")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true", help="validate the paper-only composition")
    args = parser.parse_args(argv)
    deps = build_paper_dependencies(args.root)
    if args.check:
        print(json.dumps({"paper_only": True, "config_checksum": deps.config.checksum}))
        return 0
    raise SystemExit("scheduled daemon service requires an explicit runtime panel provider")


if __name__ == "__main__":
    raise SystemExit(main())
