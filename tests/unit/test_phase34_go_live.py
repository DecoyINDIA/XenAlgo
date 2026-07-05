"""
Executable specifications for Phase 3.4 go-live checklist evidence.

Covers: PRD G2/G3/G4/G6, TRD deployment and ops gates, G3 go-live criteria,
SI-5/SI-10/SI-12. No test touches the Dhan API or places a live order.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

phase34 = pytest.importorskip("xenalgo.phase34")


def _evidence(**overrides):
    values = dict(
        activated_at=dt.datetime(2026, 8, 16, 8, 0),
        live_host_id="aws-mumbai-live-1",
        config_checksum="sha256:go-live-10pct",
        phase0_foundation_passed=True,
        phase1_execution_core_passed=True,
        phase2_console_passed=True,
        phase31_failure_injection_passed=True,
        phase32_burn_in_passed=True,
        phase32_live_host_readiness_passed=True,
        phase33_post_migration_passed=True,
        static_ip_verified_at=dt.datetime(2026, 8, 15, 8, 0),
        token_refresh_sessions=5,
        backup_restore_drill_at=dt.date(2026, 8, 14),
        broker_kill_switch_verified_at=dt.datetime(2026, 8, 15, 10, 0),
        phone_alerts_confirmed_at=dt.datetime(2026, 8, 15, 10, 30),
        dedicated_account_funded=True,
        operator_approval_id="approval-2026-08-16",
        live_trading_enabled=True,
        broker_order_api_enabled=True,
        live_trading_mode="live",
        capital_fraction=0.10,
        governor_max_orders_per_sec=2,
    )
    values.update(overrides)
    return phase34.GoLiveChecklistEvidence(**values)


def test_go_live_activation_passes_with_full_checklist_and_ten_percent_capital():
    report = phase34.GoLiveChecklistReview().evaluate(_evidence())

    assert report.passed is True


def test_go_live_pre_activation_review_passes_while_live_flags_remain_off():
    report = phase34.GoLiveChecklistReview().evaluate(
        _evidence(
            live_trading_enabled=False,
            broker_order_api_enabled=False,
            live_trading_mode="paper",
        ),
        require_activation=False,
    )

    assert report.passed is True


def test_go_live_checklist_fails_closed_on_missing_or_unsafe_evidence():
    report = phase34.GoLiveChecklistReview().evaluate(
        _evidence(
            activated_at=dt.datetime(2026, 8, 17, 10, 0),
            live_host_id="",
            config_checksum="",
            phase0_foundation_passed=False,
            phase1_execution_core_passed=False,
            phase2_console_passed=False,
            phase31_failure_injection_passed=False,
            phase32_burn_in_passed=False,
            phase32_live_host_readiness_passed=False,
            phase33_post_migration_passed=False,
            static_ip_verified_at=dt.datetime(2026, 8, 18, 8, 0),
            token_refresh_sessions=4,
            backup_restore_drill_at=dt.date(2026, 8, 18),
            broker_kill_switch_verified_at=None,
            phone_alerts_confirmed_at=None,
            dedicated_account_funded=False,
            operator_approval_id="",
            capital_fraction=0.25,
            governor_max_orders_per_sec=3,
            live_trading_enabled=False,
            broker_order_api_enabled=False,
            live_trading_mode="paper",
        )
    )

    assert report.passed is False
    rendered = " | ".join(report.blockers)
    assert "G0 foundation" in rendered
    assert "G1 execution-core" in rendered
    assert "G2 console" in rendered
    assert "Phase 3.1 failure-injection" in rendered
    assert "Phase 3.2 burn-in" in rendered
    assert "Phase 3.2 live-host readiness" in rendered
    assert "Phase 3.3 post-migration" in rendered
    assert "live host id is missing" in rendered
    assert "config checksum" in rendered
    assert "static IP was verified after" in rendered
    assert "token-refresh sessions" in rendered
    assert "restore drill" in rendered
    assert "broker-side kill switch" in rendered
    assert "real-phone alert" in rendered
    assert "dedicated funded account" in rendered
    assert "operator approval" in rendered
    assert "25.0%" in rendered
    assert "max_orders_per_sec is 3" in rendered
    assert "NSE market hours" in rendered
    assert "live_trading.mode must be live" in rendered
    assert "live_trading.enabled must be true" in rendered
    assert "broker.order_api_enabled must be true" in rendered


def test_pre_activation_review_blocks_accidental_live_enablement():
    report = phase34.GoLiveChecklistReview().evaluate(
        _evidence(
            live_trading_enabled=True,
            broker_order_api_enabled=True,
            live_trading_mode="live",
        ),
        require_activation=False,
    )

    assert report.passed is False
    rendered = " | ".join(report.blockers)
    assert "live_trading.enabled must remain false" in rendered
    assert "broker.order_api_enabled must remain false" in rendered


def test_go_live_checklist_csv_loader_reads_operator_evidence():
    evidence_dir = Path(".tmp") / "test_phase34_go_live"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = evidence_dir / "phase34.csv"
    evidence.write_text(
        "activated_at,live_host_id,config_checksum,phase0_foundation_passed,"
        "phase1_execution_core_passed,phase2_console_passed,"
        "phase31_failure_injection_passed,phase32_burn_in_passed,"
        "phase32_live_host_readiness_passed,phase33_post_migration_passed,"
        "static_ip_verified_at,token_refresh_sessions,backup_restore_drill_at,"
        "broker_kill_switch_verified_at,phone_alerts_confirmed_at,"
        "dedicated_account_funded,operator_approval_id,live_trading_enabled,"
        "broker_order_api_enabled,live_trading_mode,capital_fraction,"
        "governor_max_orders_per_sec\n"
        "2026-08-16T08:00:00,aws-mumbai-live-1,sha256:go-live,true,true,true,"
        "true,true,true,true,2026-08-15T08:00:00,5,2026-08-14,"
        "2026-08-15T10:00:00,2026-08-15T10:30:00,true,approval-1,true,true,"
        "live,0.10,2\n",
        encoding="utf-8",
    )

    records = phase34.load_go_live_checklist_csv(evidence)

    assert len(records) == 1
    assert records[0].live_host_id == "aws-mumbai-live-1"
    assert phase34.GoLiveChecklistReview().evaluate(records).passed is True
