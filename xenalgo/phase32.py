from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_SLEEVES = ("std30", "alpha_027", "alpha_062")


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
class BurnInRecord:
    """One sleeve's daily paper-vs-backtest observation for Phase 3.2a."""

    trading_date: dt.date
    sleeve: str
    paper_return: float
    backtest_return: float
    token_refresh_ok: bool = True
    safety_incidents: int = 0
    unexplained_outlier: bool = False
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "BurnInRecord":
        return cls(
            trading_date=_as_date(row["trading_date"]),
            sleeve=row["sleeve"],
            paper_return=float(row["paper_return"]),
            backtest_return=float(row["backtest_return"]),
            token_refresh_ok=_as_bool(row.get("token_refresh_ok", "true")),
            safety_incidents=int(row.get("safety_incidents", "0") or 0),
            unexplained_outlier=_as_bool(row.get("unexplained_outlier", "false")),
            notes=row.get("notes", ""),
        )

    @property
    def absolute_deviation(self) -> float:
        return abs(self.paper_return - self.backtest_return)

    def within_tolerance(self, tolerance_abs: float) -> bool:
        return self.absolute_deviation <= tolerance_abs


@dataclass(frozen=True)
class BurnInPolicy:
    required_calendar_days: int = 28
    min_reviewed_trading_days: int = 18
    tolerance_abs: float = 0.005
    min_within_tolerance_ratio: float = 0.90
    expected_sleeves: tuple[str, ...] = DEFAULT_SLEEVES


@dataclass(frozen=True)
class BurnInSummary:
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


def load_burn_in_csv(path: str | Path) -> list[BurnInRecord]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [BurnInRecord.from_row(row) for row in csv.DictReader(fh)]


class BurnInReview:
    """Evaluates the repository-verifiable evidence gate for Phase 3.2a."""

    def __init__(self, policy: BurnInPolicy | None = None) -> None:
        self.policy = policy or BurnInPolicy()

    def evaluate(self, records: Iterable[BurnInRecord]) -> BurnInSummary:
        ordered = sorted(records, key=lambda rec: (rec.trading_date, rec.sleeve))
        if not ordered:
            return BurnInSummary(None, None, 0, 0, 0.0, 0, ("no burn-in records supplied",))

        policy = self.policy
        dates = sorted({rec.trading_date for rec in ordered})
        start = dates[0]
        end = dates[-1]
        calendar_days = (end - start).days + 1
        blockers: list[str] = []

        if calendar_days < policy.required_calendar_days:
            blockers.append(
                f"burn-in span is {calendar_days} calendar days; "
                f"requires at least {policy.required_calendar_days}"
            )
        if len(dates) < policy.min_reviewed_trading_days:
            blockers.append(
                f"only {len(dates)} reviewed trading days; "
                f"requires at least {policy.min_reviewed_trading_days}"
            )

        expected = set(policy.expected_sleeves)
        by_date: dict[dt.date, set[str]] = {}
        for rec in ordered:
            by_date.setdefault(rec.trading_date, set()).add(rec.sleeve)
        for day, sleeves in sorted(by_date.items()):
            missing = sorted(expected - sleeves)
            if missing:
                blockers.append(f"{day.isoformat()} missing sleeve reviews: {', '.join(missing)}")

        within = sum(1 for rec in ordered if rec.within_tolerance(policy.tolerance_abs))
        ratio = within / len(ordered)
        if ratio < policy.min_within_tolerance_ratio:
            blockers.append(
                f"{ratio:.1%} of sleeve-days within tolerance; "
                f"requires at least {policy.min_within_tolerance_ratio:.0%}"
            )

        incident_count = sum(rec.safety_incidents for rec in ordered)
        if incident_count:
            blockers.append(f"{incident_count} safety incidents recorded during burn-in")

        if any(rec.unexplained_outlier for rec in ordered):
            blockers.append("one or more unexplained outliers remain open")

        token_sessions = len({rec.trading_date for rec in ordered if rec.token_refresh_ok})
        token_failures = sorted({rec.trading_date for rec in ordered if not rec.token_refresh_ok})
        if token_failures:
            rendered = ", ".join(day.isoformat() for day in token_failures)
            blockers.append(f"token refresh failed on: {rendered}")

        return BurnInSummary(
            start_date=start,
            end_date=end,
            reviewed_trading_days=len(dates),
            total_records=len(ordered),
            within_tolerance_ratio=ratio,
            token_refresh_sessions=token_sessions,
            blockers=tuple(blockers),
        )


@dataclass(frozen=True)
class LiveHostEvidence:
    """Operator-supplied evidence for Phase 3.2b live-host migration readiness."""

    provider: str
    region: str
    static_ip_primary: str
    static_ip_secondary: str
    static_ip_registered_at: dt.date | None
    docker_image_ref: str
    systemd_unit_enabled: bool
    backups_configured: bool
    restore_drill_at: dt.date | None
    heartbeat_configured: bool
    oracle_retained_as_staging: bool
    live_trading_enabled: bool
    broker_order_api_enabled: bool


@dataclass(frozen=True)
class HostReadinessReport:
    blockers: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.blockers


def evaluate_live_host_readiness(
    evidence: LiveHostEvidence,
    *,
    as_of: str | dt.date,
    min_static_ip_lead_days: int = 7,
) -> HostReadinessReport:
    today = _as_date(as_of)
    blockers: list[str] = []

    if not evidence.provider.strip():
        blockers.append("live host provider is not selected")
    if not evidence.region.strip():
        blockers.append("live host region is not recorded")
    if not any(token in evidence.region.lower() for token in ("ap-south-1", "mumbai", "blr", "bangalore")):
        blockers.append("live host is not evidenced in the approved India-region set")
    if not evidence.static_ip_primary.strip() or not evidence.static_ip_secondary.strip():
        blockers.append("primary and secondary static IPs are both required")
    if evidence.static_ip_registered_at is None:
        blockers.append("Dhan static-IP registration date is missing")
    else:
        registered_age_days = (today - evidence.static_ip_registered_at).days
        if registered_age_days < min_static_ip_lead_days:
            blockers.append(
                f"static IP registration age is {registered_age_days} days; "
                f"requires at least {min_static_ip_lead_days}"
            )
    if not evidence.docker_image_ref.strip():
        blockers.append("portable Docker image reference is missing")
    if not evidence.systemd_unit_enabled:
        blockers.append("systemd supervision is not enabled")
    if not evidence.backups_configured:
        blockers.append("nightly backups are not configured")
    if evidence.restore_drill_at is None or evidence.restore_drill_at > today:
        blockers.append("successful restore drill is not evidenced")
    if not evidence.heartbeat_configured:
        blockers.append("external heartbeat is not configured")
    if not evidence.oracle_retained_as_staging:
        blockers.append("Oracle instance is not retained as warm staging")
    if evidence.live_trading_enabled:
        blockers.append("live_trading.enabled must remain false before the go-live gate")
    if evidence.broker_order_api_enabled:
        blockers.append("broker.order_api_enabled must remain false before the go-live gate")

    return HostReadinessReport(tuple(blockers))
