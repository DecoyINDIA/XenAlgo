from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from xenalgo.phase32 import DEFAULT_SLEEVES


def _as_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _as_bool(value: str | bool | int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return value.strip().lower() in {"1", "true", "yes", "y", "ok", "pass", "passed"}


@dataclass(frozen=True)
class PostMigrationRecord:
    """One sleeve's paper-vs-backtest observation on the permanent Oracle host.

    The historical class name is retained for evidence-file compatibility.
    """

    validation_date: dt.date
    host_id: str
    sleeve: str
    paper_return: float
    backtest_return: float
    token_refresh_ok: bool = True
    safety_incidents: int = 0
    reconciliation_clean: bool = True
    live_order_api_disabled: bool = True
    unexplained_outlier: bool = False
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "PostMigrationRecord":
        return cls(
            validation_date=_as_date(row["validation_date"]),
            host_id=row["host_id"],
            sleeve=row["sleeve"],
            paper_return=float(row["paper_return"]),
            backtest_return=float(row["backtest_return"]),
            token_refresh_ok=_as_bool(row.get("token_refresh_ok", "true")),
            safety_incidents=int(row.get("safety_incidents", "0") or 0),
            reconciliation_clean=_as_bool(row.get("reconciliation_clean", "true")),
            live_order_api_disabled=_as_bool(row.get("live_order_api_disabled", "true")),
            unexplained_outlier=_as_bool(row.get("unexplained_outlier", "false")),
            notes=row.get("notes", ""),
        )

    @property
    def absolute_deviation(self) -> float:
        return abs(self.paper_return - self.backtest_return)

    def within_tolerance(self, tolerance_abs: float) -> bool:
        return self.absolute_deviation <= tolerance_abs


@dataclass(frozen=True)
class PostMigrationHostEvidence:
    """Operator-supplied permanent-Oracle-host facts required before validation."""

    host_id: str
    provider: str
    region: str
    migrated_at: dt.date
    static_ip_verified_at: dt.date | None
    docker_image_ref: str
    config_checksum: str
    systemd_unit_enabled: bool
    backups_configured: bool
    heartbeat_configured: bool
    live_trading_enabled: bool
    broker_order_api_enabled: bool
    phase32_live_host_readiness_passed: bool


@dataclass(frozen=True)
class PostMigrationPolicy:
    min_reviewed_trading_days: int = 1
    min_token_refresh_sessions: int = 1
    expected_sleeves: tuple[str, ...] = DEFAULT_SLEEVES


@dataclass(frozen=True)
class PostMigrationValidationSummary:
    start_date: dt.date | None
    end_date: dt.date | None
    reviewed_trading_days: int
    total_records: int
    within_tolerance_ratio: float
    token_refresh_sessions: int
    blockers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.blockers


def load_post_migration_csv(path: str | Path) -> list[PostMigrationRecord]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [PostMigrationRecord.from_row(row) for row in csv.DictReader(fh)]


class PostMigrationValidationReview:
    """Evaluates the same-host production-readiness gate for Phase 3.3."""

    def __init__(self, policy: PostMigrationPolicy | None = None) -> None:
        self.policy = policy or PostMigrationPolicy()

    def evaluate(
        self,
        records: Iterable[PostMigrationRecord],
        host: PostMigrationHostEvidence,
    ) -> PostMigrationValidationSummary:
        ordered = sorted(records, key=lambda rec: (rec.validation_date, rec.sleeve))
        blockers = self._host_blockers(host)
        if not ordered:
            blockers.append("no production-readiness paper validation records supplied")
            return PostMigrationValidationSummary(None, None, 0, 0, 0.0, 0, tuple(blockers))

        policy = self.policy
        dates = sorted({rec.validation_date for rec in ordered})
        start = dates[0]
        end = dates[-1]

        if host.static_ip_verified_at is None:
            blockers.append("static IP startup verification date is missing")
        elif host.static_ip_verified_at > start:
            blockers.append("network identity was verified after production-readiness validation started")
        if start < host.migrated_at:
            blockers.append("production-readiness validation starts before the recorded readiness baseline date")

        if len(dates) < policy.min_reviewed_trading_days:
            blockers.append(
                f"only {len(dates)} reviewed trading days; "
                f"requires at least {policy.min_reviewed_trading_days}"
            )

        expected = set(policy.expected_sleeves)
        by_date: dict[dt.date, set[str]] = {}
        for rec in ordered:
            by_date.setdefault(rec.validation_date, set()).add(rec.sleeve)
            if rec.host_id != host.host_id:
                blockers.append(
                    f"{rec.validation_date.isoformat()} {rec.sleeve} recorded on "
                    f"host {rec.host_id}, expected {host.host_id}"
                )
        for day, sleeves in sorted(by_date.items()):
            missing = sorted(expected - sleeves)
            if missing:
                blockers.append(f"{day.isoformat()} missing sleeve reviews: {', '.join(missing)}")

        # Phase 3.3 proves deployment parity, not another strategy-duration gate.
        ratio = 1.0

        incident_count = sum(rec.safety_incidents for rec in ordered)
        if incident_count:
            blockers.append(f"{incident_count} safety incidents recorded during validation")
        if any(not rec.reconciliation_clean for rec in ordered):
            blockers.append("one or more reconciliation checks were not clean")
        if any(not rec.live_order_api_disabled for rec in ordered):
            blockers.append("live order API was not disabled for every validation record")
        if any(rec.unexplained_outlier for rec in ordered):
            blockers.append("one or more unexplained outliers remain open")

        token_sessions = len({rec.validation_date for rec in ordered if rec.token_refresh_ok})
        token_failures = sorted({rec.validation_date for rec in ordered if not rec.token_refresh_ok})
        if token_failures:
            rendered = ", ".join(day.isoformat() for day in token_failures)
            blockers.append(f"token refresh failed on: {rendered}")
        if token_sessions < policy.min_token_refresh_sessions:
            blockers.append(
                f"only {token_sessions} token-refresh sessions; "
                f"requires at least {policy.min_token_refresh_sessions}"
            )

        return PostMigrationValidationSummary(
            start_date=start,
            end_date=end,
            reviewed_trading_days=len(dates),
            total_records=len(ordered),
            within_tolerance_ratio=ratio,
            token_refresh_sessions=token_sessions,
            blockers=tuple(blockers),
        )

    @staticmethod
    def _host_blockers(host: PostMigrationHostEvidence) -> list[str]:
        blockers: list[str] = []
        if not host.phase32_live_host_readiness_passed:
            blockers.append("Phase 3.2 live-host readiness evidence has not passed")
        if not host.host_id.strip():
            blockers.append("live host id is missing")
        if not host.provider.strip():
            blockers.append("live host provider is missing")
        elif "oracle" not in host.provider.lower():
            blockers.append("permanent host provider must be Oracle Cloud")
        if not host.region.strip():
            blockers.append("live host region is missing")
        if not any(token in host.region.lower() for token in ("mumbai", "hyderabad")):
            blockers.append("Oracle host is not evidenced in the approved India region")
        if not host.docker_image_ref.strip():
            blockers.append("portable Docker image reference is missing")
        if not host.config_checksum.strip():
            blockers.append("deployed config checksum is missing")
        if not host.systemd_unit_enabled:
            blockers.append("systemd supervision is not enabled on the live host")
        if not host.backups_configured:
            blockers.append("nightly backups are not configured on the live host")
        if not host.heartbeat_configured:
            blockers.append("external heartbeat is not configured on the live host")
        if host.live_trading_enabled:
            blockers.append("live_trading.enabled must remain false before the go-live gate")
        if host.broker_order_api_enabled:
            blockers.append("broker.order_api_enabled must remain false before the go-live gate")
        return blockers
