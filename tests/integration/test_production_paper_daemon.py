"""B2 production paper composition specs. Covers FR-2/FR-6/FR-13/FR-17 and SI-3/4/5/6/8/9/10."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from xenalgo.broker.governor import OrderGovernor
from xenalgo.broker.paper import PaperBroker
from xenalgo.broker.token import Token, TokenManager
from xenalgo.config import RuntimeConfig
from xenalgo.execution import Journal
from xenalgo.monolith import PaperOrderPlan
from xenalgo.ops import KillSwitch
from xenalgo.paper_daemon import (
    PaperDependencies,
    ProductionPaperDaemon,
    ScheduledPaperRuntime,
    StartupBlocked,
)
from xenalgo.risk import RiskEngine
from xenalgo.scheduler import MarketCalendar, RebalancePlan


def _deps(tmp_path: Path, broker: PaperBroker | None = None) -> PaperDependencies:
    now = dt.datetime(2026, 7, 13, 3, 0, tzinfo=dt.UTC)
    config = RuntimeConfig(
        "live",
        tmp_path / "config.yaml",
        {
            "live_trading": {"enabled": False, "mode": "paper"},
            "broker": {"provider": "fyers", "order_api_enabled": False},
        },
        "config-sha256",
    )
    journal = Journal(tmp_path / "paper.sqlite3")
    return PaperDependencies(
        config=config,
        broker=broker or PaperBroker(ltp={"SBIN": 100.0}),
        journal=journal,
        token_manager=TokenManager(
            tmp_path / "token.sqlite3",
            token_provider=lambda: Token("redacted", now + dt.timedelta(hours=8)),
            clock=lambda: now,
        ),
        risk_engine=RiskEngine(
            {
                "max_order_notional_inr": 200_000,
                "max_pct_of_adv": 0.05,
                "price_collar_pct": 0.03,
                "max_position_pct": 0.10,
                "fee_buffer_pct": 0.0,
            }
        ),
        governor=OrderGovernor(),
        kill_switch=KillSwitch(tmp_path / "paper.sqlite3"),
    )


def _panel(day: dt.date):
    index = pd.DatetimeIndex([pd.Timestamp(day)])
    return {
        "close": pd.DataFrame({"SBIN": [100.0]}, index=index),
        "volume": pd.DataFrame({"SBIN": [1_000_000]}, index=index),
    }


def _order(day: dt.date) -> PaperOrderPlan:
    return PaperOrderPlan(f"{day}:std30:SBIN:BUY:1", "std30", "SBIN", "SBIN", "BUY", 10, 100.0)


def test_complete_scheduled_paper_session_is_evidenced_and_restart_is_idempotent(tmp_path):
    day = dt.date(2026, 7, 13)
    deps = _deps(tmp_path)
    daemon = ProductionPaperDaemon(deps, evidence_dir=tmp_path / "evidence", host_id="test-host")

    first = daemon.run_session(trading_date=day, panel=_panel(day), orders=[_order(day)])
    restarted = ProductionPaperDaemon(deps, evidence_dir=tmp_path / "evidence", host_id="test-host")
    second = restarted.run_session(trading_date=day, panel=_panel(day), orders=[_order(day)])

    assert first.submitted == first.filled == 1
    assert first.reconciliation_clean is True
    assert first.evidence_checksum
    assert second.submitted == second.filled == 0
    assert deps.broker.holdings == {"SBIN": 10}
    assert len([event for event in deps.journal.events() if event["state"] == "INTENT"]) == 1


def test_non_rebalance_session_places_no_orders(tmp_path):
    day = dt.date(2026, 7, 13)  # Monday
    daemon = ProductionPaperDaemon(_deps(tmp_path), evidence_dir=tmp_path / "evidence")
    result = daemon.run_session(
        trading_date=day,
        panel=_panel(day),
        orders=[_order(day)],
        rebalance=RebalancePlan("weekly", 4),
    )
    assert result.rebalance_session is False
    assert result.submitted == result.filled == 0


def test_holiday_and_kill_switch_fail_startup_closed(tmp_path):
    day = dt.date(2026, 7, 13)
    deps = _deps(tmp_path)
    deps.calendar = MarketCalendar({day: "holiday"})
    daemon = ProductionPaperDaemon(deps, evidence_dir=tmp_path / "evidence")
    with pytest.raises(StartupBlocked, match="calendar"):
        daemon.startup(trading_date=day, panel=_panel(day))

    deps.calendar = MarketCalendar()
    deps.kill_switch.activate("test")
    with pytest.raises(StartupBlocked, match="controls"):
        daemon.startup(trading_date=day, panel=_panel(day))


def test_production_composition_rejects_any_paper_broker_subclass(tmp_path):
    class UnsafeBroker(PaperBroker):
        pass

    with pytest.raises(TypeError, match="concrete PaperBroker"):
        _deps(tmp_path, UnsafeBroker())


def test_clock_controlled_runtime_executes_all_jobs_once(tmp_path):
    day = dt.date(2026, 7, 13)
    daemon = ProductionPaperDaemon(_deps(tmp_path), evidence_dir=tmp_path / "evidence")
    calls = {"backup": 0, "heartbeat": 0}
    runtime = ScheduledPaperRuntime(
        daemon,
        panel_provider=lambda _day: _panel(day),
        order_provider=lambda _day, _panel_value: [_order(day)],
        backup=lambda: calls.__setitem__("backup", calls["backup"] + 1),
        heartbeat=lambda: calls.__setitem__("heartbeat", calls["heartbeat"] + 1),
    )

    result = runtime.run_trading_day(day)
    runtime.run_trading_day(day)

    assert result.submitted == result.filled == 1
    assert len(runtime.completed) == 8
    assert calls == {"backup": 1, "heartbeat": 1}
