"""Offline executable specifications for deployment gates D0-D2 and D8."""
from __future__ import annotations

import sqlite3

from xenalgo.deployment import (
    HostReadinessEvidence, OperationsHandoffEvidence, PaperDeploymentEvidence,
    ReleaseEvidence, evaluate_d0, evaluate_d1, evaluate_d2, evaluate_d8,
    sqlite_backup, verify_paper_config, verify_sqlite_restore,
)


def test_d0_release_acceptance_passes_only_with_immutable_safe_evidence():
    evidence = ReleaseEvidence("abc", True, True, "x@sha256:1", "sha256:1", "sha256:2", "sha256:3", "v1", "sha256:4", "sha256:5", True, True, True, True, True, True, "approval-paper")
    assert evaluate_d0(evidence).passed
    assert not evaluate_d0(dataclasses_replace(evidence, live_trading_enabled=True)).passed


def test_d1_host_readiness_is_fail_closed():
    evidence = HostReadinessEvidence("oci-1", "oracle", "ap-mumbai-1", "Oracle Linux 9", "100.64.0.1", True, True, True, True, True, 2.0, "26.1", "252", True, True, True, True, True, True, True, True)
    assert evaluate_d1(evidence).passed
    report = evaluate_d1(dataclasses_replace(evidence, public_app_port_refused=False, clock_offset_ms=1500))
    assert not report.passed and "public application port" in " ".join(report.blockers)


def test_d2_requires_identity_recovery_restore_and_zero_real_calls():
    evidence = PaperDeploymentEvidence(
        deployed_outside_market_hours=True, kill_state_confirmed=True,
        prior_state_backup_checksum="sha256:b", image_digest="sha256:i",
        config_checksum="sha256:c", d0_image_digest="sha256:i", d0_config_checksum="sha256:c",
        ownership_verified=True, secrets_excluded_from_backup=True, preflight_passed=True,
        service_enabled=True, heartbeat_verified=True, health_verified=True, sse_verified=True,
        tailscale_access_verified=True, public_app_port_refused=True,
        restart_replay_consistent=True, kill_blocks_within_one_second=True,
        synthetic_alert_verified=True, restore_replay_consistent=True,
        recovery_seconds=12.0, duplicate_intents_or_orders=0, real_order_api_calls=0,
    )
    assert evaluate_d2(evidence).passed
    report = evaluate_d2(dataclasses_replace(evidence, recovery_seconds=61, real_order_api_calls=1))
    assert not report.passed and len(report.blockers) == 2


def test_paper_config_and_sqlite_backup_restore(tmp_path):
    assert verify_paper_config("config/config.live.yaml").passed
    source, backup = tmp_path / "journal.sqlite", tmp_path / "backups" / "journal.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("create table order_events(id integer primary key, event text)")
        db.execute("insert into order_events(event) values ('INTENT')")
    assert sqlite_backup(source, backup).startswith("sha256:")
    assert verify_sqlite_restore(backup).passed
    with sqlite3.connect(backup) as db:
        assert db.execute("select event from order_events").fetchone() == ("INTENT",)


def test_d8_requires_every_operations_handoff_component():
    evidence = OperationsHandoffEvidence(*([True] * 10))
    assert evaluate_d8(evidence).passed
    assert not evaluate_d8(dataclasses_replace(evidence, hundred_percent_stage_completed=False)).passed


def dataclasses_replace(value, **changes):
    import dataclasses
    return dataclasses.replace(value, **changes)
