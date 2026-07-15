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
    build_paper_dependencies,
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


def test_paper_broker_mark_filled_fail_closed():
    # Unit test on PaperBroker.mark_filled: with no ltp entry and no avg_price,
    # the order ends REJECTED and holdings are unchanged.
    broker = PaperBroker()
    broker.place_order(SimpleNamespace(
        correlation_id="cid-no-price",
        qty=10,
        limit_price=100.0,
        side="BUY",
        symbol="SBIN",
        security_id="2885"
    ))
    # ltp is empty, avg_price not set in the order dict.
    # calling mark_filled should reject the order
    broker.mark_filled("cid-no-price")
    order = broker.get_order_by_correlation("cid-no-price")
    assert order["state"] == "REJECTED"
    assert order.get("reason") == "no paper mark price"
    assert broker.holdings.get("SBIN", 0) == 0


def test_production_paper_daemon_process_restart(tmp_path, monkeypatch):
    # Set up config and override files under tmp_path
    (tmp_path / "config").mkdir()
    config_data = {
        "profile": "live",
        "live_trading": {"enabled": False, "mode": "paper"},
        "sleeves": {"std30": {"capital_fraction": 1.0, "enabled": True}},
        "risk": {"max_order_notional_inr": 200000, "max_pct_of_adv": 0.05, "price_collar_pct": 0.03, "max_position_pct": 0.10},
        "execution": {"order_type": "MARKETABLE_LIMIT", "buy_collar_pct": 0.005},
        "governor": {"max_orders_per_sec": 2, "max_orders_per_day": 500},
        "broker": {"provider": "fyers", "fyers_sdk_version": "external-injected", "token_store": ".xenalgo-secrets/fyers_token.sqlite", "order_api_enabled": False},
        "storage": {"journal_sqlite": "Diary/state/order_journal.sqlite"},
        "scheduler": {"overrides_file": "config/nse_overrides.yaml"},
        "alerts": {},
        "web": {"bind_port": 8080},
        "logging": {"level": "INFO", "format": "json", "file_path": "Diary/logs/xenalgo.log"}
    }
    with open(tmp_path / "config" / "config.live.yaml", "w") as f:
        import yaml
        yaml.safe_dump(config_data, f)
    
    # Create empty overrides file
    (tmp_path / "config" / "nse_overrides.yaml").write_text("holidays: []\nspecial_sessions: []\n")
    
    # Create token path directory
    (tmp_path / ".xenalgo-secrets").mkdir(parents=True, exist_ok=True)
    
    # Day 1 rebalance session: BUY 10 SBIN
    day1 = dt.date(2026, 7, 13)
    deps1 = build_paper_dependencies(tmp_path)
    # mock token manager to be valid
    monkeypatch.setattr(deps1.token_manager, "ensure_valid", lambda: SimpleNamespace(value="valid-token"))
    
    # Seeding ltp in deps1.broker before run
    deps1.broker.ltp["SBIN"] = 100.0
    
    daemon1 = ProductionPaperDaemon(deps1, evidence_dir=tmp_path / "evidence", host_id="test-host")
    
    # We construct the PaperOrderPlan
    plan = PaperOrderPlan("std30:SBIN:2026-07-13", "std30", "SBIN", "2885", "BUY", 10, 100.0)
    
    # Run session on Day 1
    result1 = daemon1.run_session(trading_date=day1, panel=_panel(day1), orders=[plan])
    
    assert result1.submitted == result1.filled == 1
    assert result1.reconciliation_clean is True
    assert deps1.broker.holdings == {"SBIN": 10}
    assert deps1.broker.cash == 10_000_000.0 - 1000.0
    
    # Discard the daemon and broker entirely. Re-run build_paper_dependencies against the same root path.
    deps2 = build_paper_dependencies(tmp_path)
    monkeypatch.setattr(deps2.token_manager, "ensure_valid", lambda: SimpleNamespace(value="valid-token"))
    
    # Re-seed ltp for Day 2
    deps2.broker.ltp["SBIN"] = 100.0
    
    # Verify the restart reloaded cash and holdings
    assert deps2.broker.holdings == {"SBIN": 10}
    assert deps2.broker.cash == 10_000_000.0 - 1000.0
    
    # Day 2: SELL 10 SBIN
    day2 = dt.date(2026, 7, 14)
    daemon2 = ProductionPaperDaemon(deps2, evidence_dir=tmp_path / "evidence", host_id="test-host")
    plan_sell = PaperOrderPlan("std30:SBIN:2026-07-14", "std30", "SBIN", "2885", "SELL", 10, 100.0)
    
    result2 = daemon2.run_session(trading_date=day2, panel=_panel(day2), orders=[plan_sell])
    
    assert result2.submitted == result2.filled == 1
    assert result2.reconciliation_clean is True
    assert deps2.broker.holdings.get("SBIN", 0) == 0
    assert deps2.broker.cash == 10_000_000.0
    
    
def test_startup_detects_local_only_drift(tmp_path, monkeypatch):
    # Set up config and override files under tmp_path
    (tmp_path / "config").mkdir()
    config_data = {
        "profile": "live",
        "live_trading": {"enabled": False, "mode": "paper"},
        "sleeves": {"std30": {"capital_fraction": 1.0, "enabled": True}},
        "risk": {"max_order_notional_inr": 200000, "max_pct_of_adv": 0.05, "price_collar_pct": 0.03, "max_position_pct": 0.10},
        "execution": {"order_type": "MARKETABLE_LIMIT", "buy_collar_pct": 0.005},
        "governor": {"max_orders_per_sec": 2, "max_orders_per_day": 500},
        "broker": {"provider": "fyers", "fyers_sdk_version": "external-injected", "token_store": ".xenalgo-secrets/fyers_token.sqlite", "order_api_enabled": False},
        "storage": {"journal_sqlite": "Diary/state/order_journal.sqlite"},
        "scheduler": {"overrides_file": "config/nse_overrides.yaml"},
        "alerts": {},
        "web": {"bind_port": 8080},
        "logging": {"level": "INFO", "format": "json", "file_path": "Diary/logs/xenalgo.log"}
    }
    with open(tmp_path / "config" / "config.live.yaml", "w") as f:
        import yaml
        yaml.safe_dump(config_data, f)
    
    (tmp_path / "config" / "nse_overrides.yaml").write_text("holidays: []\nspecial_sessions: []\n")
    (tmp_path / ".xenalgo-secrets").mkdir(parents=True, exist_ok=True)
    
    deps = build_paper_dependencies(tmp_path)
    monkeypatch.setattr(deps.token_manager, "ensure_valid", lambda: SimpleNamespace(value="valid-token"))
    
    # 1. Seed journal with 10 SBIN, but do NOT seed broker holdings
    deps.journal.append(
        correlation_id="std30:SBIN:2026-07-13",
        state="TRADED",
        symbol="SBIN",
        side="BUY",
        filled_qty=10,
        avg_fill_price=100.0,
        raw_json={"event_key": "paper-1:TRADED:10"}
    )
    
    daemon = ProductionPaperDaemon(deps, evidence_dir=tmp_path / "evidence", host_id="test-host")
    
    # Call startup on daemon - it must raise StartupBlocked because local journal (10) != broker holdings (0)
    with pytest.raises(StartupBlocked, match="reconciliation"):
        daemon.startup(trading_date=dt.date(2026, 7, 13), panel=_panel(dt.date(2026, 7, 13)))
    
    # 2. Seed broker holdings to match journal, now startup should succeed
    deps.broker.holdings["SBIN"] = 10
    status = daemon.startup(trading_date=dt.date(2026, 7, 13), panel=_panel(dt.date(2026, 7, 13)))
    assert status.ready is True


def test_session_composition(tmp_path, monkeypatch):
    # Set up config and overrides files
    (tmp_path / "config").mkdir()
    config_data = {
        "profile": "live",
        "live_trading": {"enabled": False, "mode": "paper"},
        "sleeves": {"std30": {"capital_fraction": 1.0, "enabled": True}},
        "risk": {"max_order_notional_inr": 200000, "max_pct_of_adv": 0.05, "price_collar_pct": 0.03, "max_position_pct": 0.10},
        "execution": {"order_type": "MARKETABLE_LIMIT", "buy_collar_pct": 0.005},
        "governor": {"max_orders_per_sec": 2, "max_orders_per_day": 500},
        "broker": {"provider": "fyers", "fyers_sdk_version": "external-injected", "token_store": ".xenalgo-secrets/fyers_token.sqlite", "order_api_enabled": False},
        "storage": {"journal_sqlite": "Diary/state/order_journal.sqlite"},
        "scheduler": {"overrides_file": "config/nse_overrides.yaml"},
        "alerts": {},
        "web": {"bind_port": 8080},
        "logging": {"level": "INFO", "format": "json", "file_path": "Diary/logs/xenalgo.log"},
        "universe": {"symbols": ["SBIN"]}
    }
    with open(tmp_path / "config" / "config.live.yaml", "w") as f:
        import yaml
        yaml.safe_dump(config_data, f)
    
    (tmp_path / "config" / "nse_overrides.yaml").write_text("holidays: []\nspecial_sessions: []\n")
    (tmp_path / ".xenalgo-secrets").mkdir(parents=True, exist_ok=True)
    
    # 1. Test build_panel_provider
    fake_client = SimpleNamespace()
    
    # Mock loader.history
    dummy_history_df = pd.DataFrame({
        "date": [pd.Timestamp("2026-07-13")],
        "open": [99.0],
        "high": [101.0],
        "low": [98.0],
        "close": [100.0],
        "volume": [10000.0],
        "symbol": ["SBIN"],
        "security_id": ["2885"]
    })
    
    class FakeLoader:
        def __init__(self, client):
            pass
        def history(self, symbol, start, end):
            return dummy_history_df
            
    monkeypatch.setattr("xenalgo.session_composition.FyersHistoryLoader", FakeLoader)
    
    deps = build_paper_dependencies(tmp_path)
    monkeypatch.setattr(deps.token_manager, "ensure_valid", lambda: SimpleNamespace(value="valid-token"))
    
    from xenalgo.session_composition import build_panel_provider, build_order_provider
    panel_prov = build_panel_provider(deps.config, fake_client, ["SBIN"], warmup_days=10)
    panel = panel_prov(dt.date(2026, 7, 13))
    
    assert "close" in panel
    assert panel["close"].shape == (1, 1)
    assert panel["close"]["SBIN"].iloc[0] == 100.0
    
    # 2. Test build_order_provider
    class FakePortfolioEngine:
        def __init__(self, config_data):
            pass
        def generate_target_weights(self, factor_scores, panel):
            index = pd.DatetimeIndex([pd.Timestamp("2026-07-13")])
            return pd.DataFrame({"SBIN": [0.5]}, index=index)
            
    monkeypatch.setattr("Brain.portfolio_engine.PortfolioEngine", FakePortfolioEngine)
    
    class FakeStd30:
        @staticmethod
        def compute(panel):
            return pd.Series([1.0], index=["SBIN"])
            
    import sys
    sys.modules["Strategies.std30"] = FakeStd30
    
    from xenalgo.execution.reconcile import Reconciler
    reconciler = Reconciler(deps.broker)
    order_prov = build_order_provider(deps.config, deps.journal, reconciler)
    orders = list(order_prov(dt.date(2026, 7, 13), panel))
    
    assert len(orders) == 1
    assert orders[0].symbol == "SBIN"
    assert orders[0].side == "BUY"
    assert orders[0].qty == 50000
    assert orders[0].limit_price == 100.0


