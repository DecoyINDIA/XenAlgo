"""
Executable specifications for Phase 3.3 post-migration paper validation evidence.

Covers: PRD G3/FR-17, TRD deployment and ops gates, G3 go-live criteria.
No test touches the Fyers API or enables live order placement.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

phase33 = pytest.importorskip("xenalgo.phase33")


def _host(**overrides):
    values = dict(
        host_id="aws-mumbai-live-1",
        provider="aws",
        region="ap-south-1",
        migrated_at=dt.date(2026, 8, 1),
        static_ip_verified_at=dt.date(2026, 8, 1),
        docker_image_ref="xenalgo:phase33",
        config_checksum="sha256:abc123",
        systemd_unit_enabled=True,
        backups_configured=True,
        heartbeat_configured=True,
        live_trading_enabled=False,
        broker_order_api_enabled=False,
        phase32_live_host_readiness_passed=True,
    )
    values.update(overrides)
    return phase33.PostMigrationHostEvidence(**values)


def _clean_records() -> list[phase33.PostMigrationRecord]:
    start = dt.date(2026, 8, 3)
    records = []
    for offset in range(8):
        day = start + dt.timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for sleeve in phase33.DEFAULT_SLEEVES:
            records.append(
                phase33.PostMigrationRecord(
                    validation_date=day,
                    host_id="aws-mumbai-live-1",
                    sleeve=sleeve,
                    paper_return=0.010,
                    backtest_return=0.011,
                    token_refresh_ok=True,
                    reconciliation_clean=True,
                    live_order_api_disabled=True,
                )
            )
    return records


def test_focused_post_migration_parity_passes_with_clean_evidence():
    summary = phase33.PostMigrationValidationReview().evaluate(_clean_records(), _host())

    assert summary.passed is True
    assert summary.reviewed_trading_days == 6
    assert summary.total_records == 18
    assert summary.within_tolerance_ratio == 1.0
    assert summary.token_refresh_sessions == 6


def test_post_migration_validation_fails_closed_on_unsafe_or_incomplete_evidence():
    records = [
        phase33.PostMigrationRecord(
            validation_date=dt.date(2026, 8, 2),
            host_id="old-oracle-paper",
            sleeve="std30",
            paper_return=0.030,
            backtest_return=0.000,
            token_refresh_ok=False,
            safety_incidents=1,
            reconciliation_clean=False,
            live_order_api_disabled=False,
            unexplained_outlier=True,
        )
    ]
    host = _host(
        host_id="aws-mumbai-live-1",
        migrated_at=dt.date(2026, 8, 3),
        static_ip_verified_at=dt.date(2026, 8, 4),
        phase32_live_host_readiness_passed=False,
        live_trading_enabled=True,
        broker_order_api_enabled=True,
    )

    summary = phase33.PostMigrationValidationReview().evaluate(records, host)

    assert summary.passed is False
    rendered = " | ".join(summary.blockers)
    assert "Phase 3.2 live-host readiness" in rendered
    assert "live_trading.enabled must remain false" in rendered
    assert "broker.order_api_enabled must remain false" in rendered
    assert "verified after post-migration validation started" in rendered
    assert "starts before recorded migration date" in rendered
    assert "missing sleeve reviews" in rendered
    assert "host old-oracle-paper" in rendered
    assert "safety incidents" in rendered
    assert "reconciliation checks" in rendered
    assert "live order API was not disabled" in rendered
    assert "unexplained outliers" in rendered
    assert "token refresh failed" in rendered
    assert "token-refresh sessions" in rendered


def test_post_migration_csv_loader_reads_operator_evidence():
    evidence_dir = Path(".tmp") / "test_phase33_readiness"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = evidence_dir / "post_migration.csv"
    evidence.write_text(
        "validation_date,host_id,sleeve,paper_return,backtest_return,token_refresh_ok,"
        "safety_incidents,reconciliation_clean,live_order_api_disabled,unexplained_outlier,notes\n"
        "2026-08-03,aws-mumbai-live-1,std30,0.010,0.011,true,0,true,true,false,clean\n",
        encoding="utf-8",
    )

    records = phase33.load_post_migration_csv(evidence)

    assert len(records) == 1
    assert records[0].validation_date == dt.date(2026, 8, 3)
    assert records[0].host_id == "aws-mumbai-live-1"
    assert records[0].within_tolerance(0.005) is True


def test_post_migration_host_evidence_requires_live_host_ops_controls():
    summary = phase33.PostMigrationValidationReview().evaluate(
        _clean_records(),
        _host(
            provider="",
            region="us-east-1",
            docker_image_ref="",
            config_checksum="",
            systemd_unit_enabled=False,
            backups_configured=False,
            heartbeat_configured=False,
        ),
    )

    assert summary.passed is False
    rendered = " | ".join(summary.blockers)
    assert "provider is missing" in rendered
    assert "approved India-region" in rendered
    assert "Docker image reference is missing" in rendered
    assert "config checksum is missing" in rendered
    assert "systemd supervision is not enabled" in rendered
    assert "nightly backups are not configured" in rendered
    assert "external heartbeat is not configured" in rendered
