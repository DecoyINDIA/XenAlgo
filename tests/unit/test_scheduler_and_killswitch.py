"""
Executable specifications for the Scheduler (market-calendar awareness) and the
KillSwitch.

Covers: SI-10 (kill switch halts submission via any path), SI-11 (no deploy in
market hours), trading-window and holiday guards. Requirements FR-2, FR-12.

Skips until the respective xenalgo modules exist (Phase 1).
"""
from __future__ import annotations

import datetime as _dt

import pytest

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


# ─────────────────────────── Scheduler ──────────────────────────────────
sched = pytest.importorskip("xenalgo.scheduler")


def test_weekend_is_not_a_trading_day():
    cal = sched.MarketCalendar()
    assert cal.is_trading_day(_dt.date(2026, 7, 4)) is False   # Saturday
    assert cal.is_trading_day(_dt.date(2026, 7, 5)) is False   # Sunday


def test_manual_override_holiday_respected():
    cal = sched.MarketCalendar(overrides={_dt.date(2026, 7, 1): "special holiday"})
    assert cal.is_trading_day(_dt.date(2026, 7, 1)) is False


@pytest.mark.parametrize("hhmm,expected", [
    ((9, 20), False),    # opening volatility guard
    ((15, 5), True),     # inside execution window
    ((15, 25), False),   # after window
    ((11, 0), False),    # mid-day: not an execution window for swing rebalance
])
def test_execution_window_guard(hhmm, expected):
    win = sched.ExecutionWindow(start="15:00", end="15:20",
                                block_open_until="09:30")
    t = _dt.time(*hhmm)
    assert win.is_open(t) is expected


def test_rebalance_only_on_configured_day():
    plan = sched.RebalancePlan(freq="Weekly", day=0)   # Monday
    assert plan.is_rebalance_day(_dt.date(2026, 6, 29)) is True    # Monday
    assert plan.is_rebalance_day(_dt.date(2026, 6, 30)) is False   # Tuesday


# ─────────────────────────── KillSwitch ─────────────────────────────────
ops = pytest.importorskip("xenalgo.ops")


@pytest.mark.parametrize("path", ["dashboard", "telegram", "broker"])
def test_kill_switch_blocks_submission_from_any_path(tmp_journal, path):
    ks = ops.KillSwitch(store=tmp_journal)
    assert ks.is_active() is False
    ks.activate(source=path)
    assert ks.is_active() is True
    # ExecutionEngine consults this before every submit.
    assert ks.allow_submission() is False


def test_kill_switch_persists_across_restart(tmp_journal):
    ops.KillSwitch(store=tmp_journal).activate(source="telegram")
    # Fresh instance (simulated restart) reads persisted state.
    assert ops.KillSwitch(store=tmp_journal).is_active() is True


def test_no_deploy_during_market_hours():
    guard = ops.DeployGuard()
    assert guard.deploy_allowed(_dt.datetime(2026, 7, 1, 12, 0, tzinfo=IST)) is False
    assert guard.deploy_allowed(_dt.datetime(2026, 7, 1, 18, 0, tzinfo=IST)) is True


def test_market_calendar_from_overrides_file(tmp_path):
    overrides_file = tmp_path / "nse_overrides.yaml"
    overrides_file.write_text(
        "holidays:\n"
        "  - '2026-07-01'\n"
        "special_sessions:\n"
        "  - '2026-07-04'\n"
    )
    
    cal = sched.MarketCalendar.from_overrides_file(overrides_file)
    
    # 2026-07-01 is Wednesday but overridden as a holiday
    assert cal.is_trading_day(_dt.date(2026, 7, 1)) is False
    
    # 2026-07-04 is Saturday but overridden as a special session
    assert cal.is_trading_day(_dt.date(2026, 7, 4)) is True
    
    # Non-existent file defaults to standard calendar
    cal_empty = sched.MarketCalendar.from_overrides_file(tmp_path / "missing.yaml")
    assert cal_empty.is_trading_day(_dt.date(2026, 7, 1)) is True

