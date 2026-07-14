"""Fail-closed deployment evidence gates for XenAlgo D0-D8.

This module only validates local/operator-supplied evidence.  It never calls a broker,
changes live flags, deploys a host, or authorizes capital.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import yaml


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclasses.dataclass(frozen=True)
class GateReport:
    gate: str
    blockers: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.blockers


@dataclasses.dataclass(frozen=True)
class ReleaseEvidence:
    commit: str
    clean_worktree: bool
    ci_passed: bool
    image_ref: str
    image_digest: str
    dependency_checksum: str
    config_checksum: str
    evidence_schema_version: str
    rollback_image_digest: str
    rollback_config_checksum: str
    full_suite_passed: bool
    coverage_passed: bool
    contract_passed: bool
    chaos_passed: bool
    research_passed: bool
    secret_scan_passed: bool
    operator_oracle_paper_approval_id: str
    live_trading_enabled: bool = False
    broker_order_api_enabled: bool = False


def evaluate_d0(evidence: ReleaseEvidence) -> GateReport:
    blockers: list[str] = []
    required_text = {
        "release commit is missing": evidence.commit,
        "immutable image reference is missing": evidence.image_ref,
        "image digest is missing": evidence.image_digest,
        "dependency checksum is missing": evidence.dependency_checksum,
        "configuration checksum is missing": evidence.config_checksum,
        "evidence schema version is missing": evidence.evidence_schema_version,
        "rollback image digest is missing": evidence.rollback_image_digest,
        "rollback configuration checksum is missing": evidence.rollback_config_checksum,
        "Oracle paper deployment approval is missing": evidence.operator_oracle_paper_approval_id,
    }
    blockers.extend(message for message, value in required_text.items() if not value.strip())
    checks = {
        "release worktree is not clean": evidence.clean_worktree,
        "CI result is not green": evidence.ci_passed,
        "full test suite is not green": evidence.full_suite_passed,
        "coverage gate is not green": evidence.coverage_passed,
        "contract gate is not green": evidence.contract_passed,
        "chaos gate is not green": evidence.chaos_passed,
        "research gate is not green": evidence.research_passed,
        "secret scan is not green": evidence.secret_scan_passed,
    }
    blockers.extend(message for message, passed in checks.items() if not passed)
    if evidence.live_trading_enabled:
        blockers.append("live_trading.enabled must remain false at D0")
    if evidence.broker_order_api_enabled:
        blockers.append("broker.order_api_enabled must remain false at D0")
    for label, value in (("image", evidence.image_digest), ("dependency", evidence.dependency_checksum),
                         ("configuration", evidence.config_checksum), ("rollback image", evidence.rollback_image_digest),
                         ("rollback configuration", evidence.rollback_config_checksum)):
        if value and not value.startswith("sha256:"):
            blockers.append(f"{label} identity is not a sha256 digest")
    return GateReport("D0", tuple(blockers))


@dataclasses.dataclass(frozen=True)
class HostReadinessEvidence:
    host_id: str
    provider: str
    region: str
    os_version: str
    tailnet_ip: str
    tailscale_healthy: bool
    loopback_or_tailnet_bind: bool
    public_app_port_refused: bool
    ssh_restricted: bool
    ntp_synchronized: bool
    clock_offset_ms: float
    docker_version: str
    systemd_version: str
    data_paths_separated: bool
    least_privilege_permissions: bool
    monitoring_enabled: bool
    heartbeat_verified: bool
    phone_alert_verified: bool
    offbox_backup_configured: bool
    secrets_excluded_from_backup: bool
    market_hours_guard_enabled: bool
    live_trading_enabled: bool = False
    broker_order_api_enabled: bool = False


def evaluate_d1(evidence: HostReadinessEvidence, *, max_clock_offset_ms: float = 1000.0) -> GateReport:
    blockers: list[str] = []
    for message, value in {
        "host id is missing": evidence.host_id,
        "provider is missing": evidence.provider,
        "region is missing": evidence.region,
        "OS version is missing": evidence.os_version,
        "tailnet IP is missing": evidence.tailnet_ip,
        "Docker version is missing": evidence.docker_version,
        "systemd version is missing": evidence.systemd_version,
    }.items():
        if not value.strip(): blockers.append(message)
    checks = {
        "Tailscale health is not proven": evidence.tailscale_healthy,
        "application bind is not restricted to loopback/tailnet": evidence.loopback_or_tailnet_bind,
        "public application port refusal is not proven": evidence.public_app_port_refused,
        "SSH restriction is not proven": evidence.ssh_restricted,
        "NTP synchronization is not proven": evidence.ntp_synchronized,
        "data/journal/log/secret path separation is not proven": evidence.data_paths_separated,
        "least-privilege permissions are not proven": evidence.least_privilege_permissions,
        "host monitoring is not enabled": evidence.monitoring_enabled,
        "external heartbeat is not verified": evidence.heartbeat_verified,
        "real-phone critical alert is not verified": evidence.phone_alert_verified,
        "off-box backup is not configured": evidence.offbox_backup_configured,
        "secret/token backup exclusion is not proven": evidence.secrets_excluded_from_backup,
        "market-hours deployment guard is not enabled": evidence.market_hours_guard_enabled,
    }
    blockers.extend(message for message, passed in checks.items() if not passed)
    if abs(evidence.clock_offset_ms) > max_clock_offset_ms:
        blockers.append(f"clock offset {evidence.clock_offset_ms:g}ms exceeds {max_clock_offset_ms:g}ms")
    if evidence.live_trading_enabled: blockers.append("live_trading.enabled must remain false at D1")
    if evidence.broker_order_api_enabled: blockers.append("broker.order_api_enabled must remain false at D1")
    return GateReport("D1", tuple(blockers))


@dataclasses.dataclass(frozen=True)
class PaperDeploymentEvidence:
    deployed_outside_market_hours: bool
    kill_state_confirmed: bool
    prior_state_backup_checksum: str
    image_digest: str
    config_checksum: str
    d0_image_digest: str
    d0_config_checksum: str
    ownership_verified: bool
    secrets_excluded_from_backup: bool
    preflight_passed: bool
    service_enabled: bool
    heartbeat_verified: bool
    health_verified: bool
    sse_verified: bool
    tailscale_access_verified: bool
    public_app_port_refused: bool
    restart_replay_consistent: bool
    kill_blocks_within_one_second: bool
    synthetic_alert_verified: bool
    restore_replay_consistent: bool
    recovery_seconds: float
    duplicate_intents_or_orders: int
    real_order_api_calls: int
    live_trading_enabled: bool = False
    broker_order_api_enabled: bool = False


def evaluate_d2(evidence: PaperDeploymentEvidence) -> GateReport:
    blockers: list[str] = []
    checks = {
        "deployment window is not proven off-market": evidence.deployed_outside_market_hours,
        "pre-deployment kill state is not confirmed": evidence.kill_state_confirmed,
        "file ownership is not verified": evidence.ownership_verified,
        "secret/token backup exclusion is not verified": evidence.secrets_excluded_from_backup,
        "paper preflight did not pass": evidence.preflight_passed,
        "paper service is not enabled": evidence.service_enabled,
        "heartbeat is not verified": evidence.heartbeat_verified,
        "health endpoint is not verified": evidence.health_verified,
        "SSE path is not verified": evidence.sse_verified,
        "Tailscale access is not verified": evidence.tailscale_access_verified,
        "public application port refusal is not verified": evidence.public_app_port_refused,
        "restart journal replay is not consistent": evidence.restart_replay_consistent,
        "kill did not block submission within one second": evidence.kill_blocks_within_one_second,
        "synthetic alert path is not verified": evidence.synthetic_alert_verified,
        "disposable restore replay is not consistent": evidence.restore_replay_consistent,
    }
    blockers.extend(message for message, passed in checks.items() if not passed)
    if not evidence.prior_state_backup_checksum.startswith("sha256:"): blockers.append("prior-state backup checksum is missing or invalid")
    if evidence.image_digest != evidence.d0_image_digest: blockers.append("deployed image digest differs from D0")
    if evidence.config_checksum != evidence.d0_config_checksum: blockers.append("deployed config checksum differs from D0")
    if evidence.recovery_seconds > 60: blockers.append("service recovery exceeds 60 seconds")
    if evidence.duplicate_intents_or_orders: blockers.append("restart produced duplicate intent/order evidence")
    if evidence.real_order_api_calls: blockers.append("real order API was called during paper deployment")
    if evidence.live_trading_enabled: blockers.append("live_trading.enabled must remain false at D2")
    if evidence.broker_order_api_enabled: blockers.append("broker.order_api_enabled must remain false at D2")
    return GateReport("D2", tuple(blockers))


@dataclasses.dataclass(frozen=True)
class OperationsHandoffEvidence:
    d0_through_d7_passed: bool
    hundred_percent_stage_completed: bool
    release_and_checksums: bool
    commissioning_parity_activation_ramp_evidence: bool
    positions_reconciliation_and_capital: bool
    backup_restore_and_incidents: bool
    risk_limits_weights_and_approvals: bool
    monitoring_and_alert_ownership: bool
    next_review_dates: bool
    known_risks_and_phase4_boundary: bool


def evaluate_d8(evidence: OperationsHandoffEvidence) -> GateReport:
    blockers = [message for message, passed in {
        "D0-D7 are not all evidenced as passed": evidence.d0_through_d7_passed,
        "100% stage clean window is incomplete": evidence.hundred_percent_stage_completed,
        "release/checksum package is incomplete": evidence.release_and_checksums,
        "commissioning/parity/activation/ramp evidence is incomplete": evidence.commissioning_parity_activation_ramp_evidence,
        "position/reconciliation/capital handoff is incomplete": evidence.positions_reconciliation_and_capital,
        "backup/restore/incident handoff is incomplete": evidence.backup_restore_and_incidents,
        "risk/weights/approval history is incomplete": evidence.risk_limits_weights_and_approvals,
        "monitoring/alert ownership is incomplete": evidence.monitoring_and_alert_ownership,
        "next restore/review dates are missing": evidence.next_review_dates,
        "known risks/Phase 4 boundary is missing": evidence.known_risks_and_phase4_boundary,
    }.items() if not passed]
    return GateReport("D8", tuple(blockers))


def verify_paper_config(path: str | Path) -> GateReport:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    blockers = []
    if raw.get("live_trading", {}).get("enabled") is not False: blockers.append("live_trading.enabled is not false")
    if str(raw.get("live_trading", {}).get("mode", "")).lower() != "paper": blockers.append("live_trading.mode is not paper")
    if raw.get("broker", {}).get("order_api_enabled") is not False: blockers.append("broker.order_api_enabled is not false")
    if raw.get("governor", {}).get("max_orders_per_sec", 999) > 2: blockers.append("governor exceeds 2 orders per second")
    return GateReport("paper-config", tuple(blockers))


def sqlite_backup(source: str | Path, destination: str | Path) -> str:
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return sha256_file(destination)


def verify_sqlite_restore(path: str | Path) -> GateReport:
    with sqlite3.connect(Path(path)) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()
    return GateReport("sqlite-restore", () if result == ("ok",) else ("SQLite integrity check failed",))


def write_manifest(path: str | Path, payload: dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(serialized, encoding="utf-8")
    return sha256_file(target)


def deployment_matrix(reports: Iterable[GateReport]) -> dict[str, dict[str, Any]]:
    return {report.gate: {"passed": report.passed, "blockers": list(report.blockers)} for report in reports}
