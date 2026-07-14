"""B2 production paper composition specs. Covers FR-2/FR-6/FR-13/FR-17 and SI-3/4/5/6/8/9/10."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from xenalgo.alerts import HeartbeatEventAlerter, InMemoryAlerter, OperatorAlerter
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
    run_host_preflight,
)
from xenalgo.risk import RiskEngine
from xenalgo.scheduler import MarketCalendar, RebalancePlan
from xenalgo.host_preflight import (
    build_alert_adapter_from_env,
    fetch_validation_panel,
    latest_completed_trading_day,
    main as host_preflight_main,
)


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


def test_host_preflight_proves_auth_startup_and_synthetic_alert(tmp_path):
    day = dt.date(2026, 7, 13)
    deps = _deps(tmp_path)
    report = run_host_preflight(
        ProductionPaperDaemon(deps, evidence_dir=tmp_path / "evidence"),
        trading_date=day,
        panel=_panel(day),
    )

    assert report.passed
    assert report.checks == {
        "authentication": True,
        "calendar": True,
        "config": True,
        "journal_replay": True,
        "data": True,
        "controls": True,
        "reconciliation": True,
        "paper_gateway": True,
        "synthetic_alert": True,
    }
    assert deps.alerts.alerter.sent[-1].kind == "application_event"


def test_host_preflight_fails_if_alert_delivery_raises(tmp_path):
    class BrokenAlerter:
        def send(self, *_args, **_kwargs):
            raise RuntimeError("delivery failed")

    day = dt.date(2026, 7, 13)
    deps = _deps(tmp_path)
    deps.alerts.alerter = BrokenAlerter()
    report = run_host_preflight(
        ProductionPaperDaemon(deps, evidence_dir=tmp_path / "evidence"),
        trading_date=day,
        panel=_panel(day),
    )

    assert not report.passed
    assert report.checks["synthetic_alert"] is False


def test_operator_alerter_delivers_application_event_to_telegram():
    calls = []
    alerter = OperatorAlerter(
        telegram_token="bot-redacted",
        telegram_chat_id="chat-redacted",
        post=lambda url, payload, timeout: calls.append((url, payload, timeout)),
    )

    alerter.send("application_event", "synthetic D2 preflight")

    assert len(calls) == 1
    assert calls[0][0].endswith("/botbot-redacted/sendMessage")
    assert calls[0][1] == {"chat_id": "chat-redacted", "text": "[application_event] synthetic D2 preflight"}


def test_latest_completed_trading_day_is_previous_session_before_close():
    assert latest_completed_trading_day(
        dt.datetime(2026, 7, 14, 3, 0, tzinfo=dt.UTC)
    ) == dt.date(2026, 7, 13)
    assert latest_completed_trading_day(
        dt.datetime(2026, 7, 13, 2, 0, tzinfo=dt.UTC)
    ) == dt.date(2026, 7, 10)


def test_read_only_fyers_history_is_converted_to_a_validation_panel():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "s": "ok",
                "candles": [
                    [1783900800, 100, 101, 99, 100, 1_000_000],
                    [1783987200, 101, 102, 100, 101, 1_100_000],
                ],
            }

    calls = []
    panel = fetch_validation_panel(
        app_id="app-redacted",
        access_token="token-redacted",
        expected_day=dt.date(2026, 7, 14),
        get=lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
    )

    assert list(panel["close"]["SBIN"]) == [100.0, 101.0]
    assert calls[0][0] == ("https://api-t1.fyers.in/data/history",)
    assert calls[0][1]["headers"]["Authorization"] == "app-redacted:token-redacted"


def test_healthchecks_event_adapter_posts_redacted_application_event(monkeypatch):
    seen = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: seen.update(request=request, timeout=timeout) or Response(),
    )
    HeartbeatEventAlerter(heartbeat_url="https://example.invalid/redacted").send(
        "application_event", "synthetic D2 preflight"
    )

    assert seen["request"].data == b"[application_event] synthetic D2 preflight"


def test_host_preflight_alert_adapter_prefers_direct_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-redacted")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat-redacted")
    adapter, channel = build_alert_adapter_from_env()
    assert isinstance(adapter, OperatorAlerter)
    assert channel == "telegram"

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    monkeypatch.setenv("XENALGO_HEARTBEAT_URL", "https://example.invalid/redacted")
    adapter, channel = build_alert_adapter_from_env()
    assert isinstance(adapter, HeartbeatEventAlerter)
    assert channel == "healthchecks"


def test_host_preflight_main_reports_only_redacted_results(monkeypatch, capsys, tmp_path):
    day = dt.date(2026, 7, 13)
    deps = SimpleNamespace(
        token_manager=SimpleNamespace(
            ensure_valid=lambda: SimpleNamespace(value="access-token-redacted")
        ),
        calendar=MarketCalendar(),
        alerts=None,
    )
    adapter = InMemoryAlerter()
    monkeypatch.setenv("XENALGO_ROOT", str(tmp_path))
    monkeypatch.setenv("FYERS_APP_ID", "app-redacted")
    monkeypatch.setattr("xenalgo.host_preflight.build_paper_dependencies", lambda _root: deps)
    monkeypatch.setattr(
        "xenalgo.host_preflight.build_alert_adapter_from_env",
        lambda: (adapter, "memory-test"),
    )
    monkeypatch.setattr("xenalgo.host_preflight.latest_completed_trading_day", lambda *_: day)
    monkeypatch.setattr("xenalgo.host_preflight.fetch_validation_panel", lambda **_: _panel(day))
    monkeypatch.setattr("xenalgo.host_preflight.ProductionPaperDaemon", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        "xenalgo.host_preflight.run_host_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(
            passed=True, checks={"authentication": True, "synthetic_alert": True}
        ),
    )

    assert host_preflight_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "alert_channel": "memory-test",
        "checks": {"authentication": True, "synthetic_alert": True},
        "live_order_api_calls": 0,
        "passed": True,
        "trading_date": "2026-07-13",
    }
    assert deps.alerts.alerter is adapter
