"""
Executable specifications for Phase 3.2 burn-in and live-host readiness evidence.

Covers: PRD G3/FR-17, TRD deployment and ops gates, G3 go-live criteria.
No test touches the Dhan API or enables live order placement.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

phase32 = pytest.importorskip("xenalgo.phase32")


def _clean_records() -> list[phase32.BurnInRecord]:
    start = dt.date(2026, 7, 6)
    records = []
    for offset in range(29):
        day = start + dt.timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for sleeve in phase32.DEFAULT_SLEEVES:
            records.append(
                phase32.BurnInRecord(
                    trading_date=day,
                    sleeve=sleeve,
                    paper_return=0.010,
                    backtest_return=0.011,
                    token_refresh_ok=True,
                )
            )
    return records


def test_four_week_burn_in_passes_when_deviation_and_safety_are_clean():
    summary = phase32.BurnInReview().evaluate(_clean_records())

    assert summary.passed is True
    assert summary.reviewed_trading_days == 21
    assert summary.total_records == 63
    assert summary.within_tolerance_ratio == 1.0
    assert summary.token_refresh_sessions == 21


def test_short_burn_in_missing_sleeves_and_outliers_fail_closed():
    records = [
        phase32.BurnInRecord(
            trading_date=dt.date(2026, 7, 6),
            sleeve="std30",
            paper_return=0.03,
            backtest_return=0.00,
            token_refresh_ok=False,
            safety_incidents=1,
            unexplained_outlier=True,
        )
    ]

    summary = phase32.BurnInReview().evaluate(records)

    assert summary.passed is False
    rendered = " | ".join(summary.blockers)
    assert "calendar days" in rendered
    assert "missing sleeve reviews" in rendered
    assert "within tolerance" in rendered
    assert "safety incidents" in rendered
    assert "unexplained outliers" in rendered
    assert "token refresh failed" in rendered


def test_burn_in_csv_loader_reads_operator_evidence():
    evidence_dir = Path(".tmp") / "test_phase32_readiness"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = evidence_dir / "burnin.csv"
    evidence.write_text(
        "trading_date,sleeve,paper_return,backtest_return,token_refresh_ok,"
        "safety_incidents,unexplained_outlier,notes\n"
        "2026-07-06,std30,0.010,0.011,true,0,false,clean\n",
        encoding="utf-8",
    )

    records = phase32.load_burn_in_csv(evidence)

    assert len(records) == 1
    assert records[0].trading_date == dt.date(2026, 7, 6)
    assert records[0].within_tolerance(0.005) is True


def test_live_host_readiness_passes_with_external_evidence_and_live_flags_off():
    evidence = phase32.LiveHostEvidence(
        provider="aws",
        region="ap-south-1",
        static_ip_primary="203.0.113.10",
        static_ip_secondary="203.0.113.11",
        static_ip_registered_at=dt.date(2026, 8, 1),
        docker_image_ref="xenalgo:phase32",
        systemd_unit_enabled=True,
        backups_configured=True,
        restore_drill_at=dt.date(2026, 8, 7),
        heartbeat_configured=True,
        oracle_retained_as_staging=True,
        live_trading_enabled=False,
        broker_order_api_enabled=False,
    )

    report = phase32.evaluate_live_host_readiness(evidence, as_of=dt.date(2026, 8, 9))

    assert report.passed is True


def test_live_host_readiness_blocks_early_ip_and_accidental_live_enablement():
    evidence = phase32.LiveHostEvidence(
        provider="",
        region="us-east-1",
        static_ip_primary="",
        static_ip_secondary="203.0.113.11",
        static_ip_registered_at=dt.date(2026, 8, 8),
        docker_image_ref="",
        systemd_unit_enabled=False,
        backups_configured=False,
        restore_drill_at=None,
        heartbeat_configured=False,
        oracle_retained_as_staging=False,
        live_trading_enabled=True,
        broker_order_api_enabled=True,
    )

    report = phase32.evaluate_live_host_readiness(evidence, as_of=dt.date(2026, 8, 9))

    assert report.passed is False
    rendered = " | ".join(report.blockers)
    assert "provider is not selected" in rendered
    assert "approved India-region" in rendered
    assert "static IP registration age" in rendered
    assert "live_trading.enabled must remain false" in rendered
    assert "broker.order_api_enabled must remain false" in rendered
