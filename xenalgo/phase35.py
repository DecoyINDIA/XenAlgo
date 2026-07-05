from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from xenalgo.phase32 import DEFAULT_SLEEVES


def _as_date(value: str | dt.date | dt.datetime) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _as_datetime(value: str | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    normalized = value.strip().replace("Z", "+00:00")
    return dt.datetime.fromisoformat(normalized)


def _as_bool(value: str | bool | int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return value.strip().lower() in {"1", "true", "yes", "y", "ok", "pass", "passed"}


@dataclass(frozen=True)
class RampStage:
    """One required live-capital ramp stage."""

    name: str
    capital_fraction: float


DEFAULT_RAMP_STAGES = (
    RampStage("10%", 0.10),
    RampStage("25%", 0.25),
    RampStage("50%", 0.50),
    RampStage("100%", 1.00),
)


@dataclass(frozen=True)
class RampPrerequisiteEvidence:
    """Operator-supplied evidence that the 10% go-live gate passed first."""

    phase34_go_live_passed: bool
    live_host_id: str
    initial_capital_fraction: float = 0.10


@dataclass(frozen=True)
class RampRecord:
    """One sleeve's reviewed live-vs-backtest observation during a ramp stage."""

    stage: str
    capital_fraction: float
    stage_started_at: dt.datetime
    stage_ended_at: dt.datetime
    trading_date: dt.date
    sleeve: str
    live_return: float
    backtest_return: float
    live_host_id: str
    config_checksum: str
    operator_approval_id: str
    governor_max_orders_per_sec: float
    safety_incidents: int = 0
    reconciliation_clean: bool = True
    broker_kill_switch_armed: bool = True
    unexplained_outlier: bool = False
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "RampRecord":
        return cls(
            stage=row["stage"],
            capital_fraction=float(row["capital_fraction"]),
            stage_started_at=_as_datetime(row["stage_started_at"]),
            stage_ended_at=_as_datetime(row["stage_ended_at"]),
            trading_date=_as_date(row["trading_date"]),
            sleeve=row["sleeve"],
            live_return=float(row["live_return"]),
            backtest_return=float(row["backtest_return"]),
            live_host_id=row.get("live_host_id", ""),
            config_checksum=row.get("config_checksum", ""),
            operator_approval_id=row.get("operator_approval_id", ""),
            governor_max_orders_per_sec=float(row.get("governor_max_orders_per_sec", "0") or 0),
            safety_incidents=int(row.get("safety_incidents", "0") or 0),
            reconciliation_clean=_as_bool(row.get("reconciliation_clean", "true")),
            broker_kill_switch_armed=_as_bool(row.get("broker_kill_switch_armed", "true")),
            unexplained_outlier=_as_bool(row.get("unexplained_outlier", "false")),
            notes=row.get("notes", ""),
        )

    @property
    def absolute_deviation(self) -> float:
        return abs(self.live_return - self.backtest_return)

    def within_tolerance(self, tolerance_abs: float) -> bool:
        return self.absolute_deviation <= tolerance_abs


@dataclass(frozen=True)
class RampPolicy:
    required_stages: tuple[RampStage, ...] = DEFAULT_RAMP_STAGES
    required_calendar_days_per_stage: int = 14
    min_reviewed_trading_days_per_stage: int = 10
    tolerance_abs: float = 0.005
    min_within_tolerance_ratio: float = 0.90
    max_orders_per_sec: float = 2.0
    expected_sleeves: tuple[str, ...] = DEFAULT_SLEEVES


@dataclass(frozen=True)
class RampValidationSummary:
    start_date: dt.date | None
    end_date: dt.date | None
    stages_reviewed: int
    total_records: int
    within_tolerance_ratio: float
    blockers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.blockers


def load_ramp_csv(path: str | Path) -> list[RampRecord]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [RampRecord.from_row(row) for row in csv.DictReader(fh)]


class CapitalRampReview:
    """Evaluates the repository-verifiable evidence gate for Phase 3.5.

    This validates supplied evidence only. It does not call Dhan, change live
    configuration, or place/modify/cancel live orders.
    """

    def __init__(self, policy: RampPolicy | None = None) -> None:
        self.policy = policy or RampPolicy()

    def evaluate(
        self,
        records: Iterable[RampRecord],
        prerequisite: RampPrerequisiteEvidence,
    ) -> RampValidationSummary:
        ordered = sorted(records, key=lambda rec: (rec.stage_started_at, rec.trading_date, rec.sleeve))
        blockers = self._prerequisite_blockers(prerequisite)
        if not ordered:
            blockers.append("no capital-ramp records supplied")
            return RampValidationSummary(None, None, 0, 0, 0.0, tuple(blockers))

        stages = self._records_by_stage(ordered)
        expected_names = [stage.name for stage in self.policy.required_stages]
        observed_names = list(stages)
        if observed_names != expected_names:
            blockers.append(
                "expected ramp stages "
                f"{' -> '.join(expected_names)}; got {' -> '.join(observed_names) or 'none'}"
            )

        previous_end: dt.datetime | None = None
        for expected in self.policy.required_stages:
            stage_records = stages.get(expected.name, [])
            if not stage_records:
                continue
            blockers.extend(self._stage_blockers(expected, stage_records, prerequisite, previous_end))
            previous_end = stage_records[0].stage_ended_at

        within = sum(1 for rec in ordered if rec.within_tolerance(self.policy.tolerance_abs))
        ratio = within / len(ordered)
        if ratio < self.policy.min_within_tolerance_ratio:
            blockers.append(
                f"{ratio:.1%} of ramp sleeve-days within tolerance; "
                f"requires at least {self.policy.min_within_tolerance_ratio:.0%}"
            )

        incident_count = sum(rec.safety_incidents for rec in ordered)
        if incident_count:
            blockers.append(f"{incident_count} safety incidents recorded during ramp")
        if any(not rec.reconciliation_clean for rec in ordered):
            blockers.append("one or more reconciliation checks were not clean during ramp")
        if any(not rec.broker_kill_switch_armed for rec in ordered):
            blockers.append("broker-side kill switch was not armed for every ramp record")
        if any(rec.unexplained_outlier for rec in ordered):
            blockers.append("one or more unexplained ramp outliers remain open")

        dates = [rec.trading_date for rec in ordered]
        return RampValidationSummary(
            start_date=min(dates),
            end_date=max(dates),
            stages_reviewed=len(stages),
            total_records=len(ordered),
            within_tolerance_ratio=ratio,
            blockers=tuple(blockers),
        )

    @staticmethod
    def _records_by_stage(records: list[RampRecord]) -> dict[str, list[RampRecord]]:
        stages: dict[str, list[RampRecord]] = {}
        for rec in records:
            stages.setdefault(rec.stage.strip(), []).append(rec)
        return stages

    @staticmethod
    def _prerequisite_blockers(prerequisite: RampPrerequisiteEvidence) -> list[str]:
        blockers: list[str] = []
        if not prerequisite.phase34_go_live_passed:
            blockers.append("Phase 3.4 go-live evidence has not passed")
        if not prerequisite.live_host_id.strip():
            blockers.append("live host id is missing")
        if abs(prerequisite.initial_capital_fraction - 0.10) > 0.000001:
            blockers.append("Phase 3.5 must start from the approved 10% live-capital stage")
        return blockers

    def _stage_blockers(
        self,
        expected: RampStage,
        records: list[RampRecord],
        prerequisite: RampPrerequisiteEvidence,
        previous_end: dt.datetime | None,
    ) -> list[str]:
        blockers: list[str] = []
        prefix = f"{expected.name} stage"
        first = records[0]

        starts = {rec.stage_started_at for rec in records}
        ends = {rec.stage_ended_at for rec in records}
        capital_fractions = {rec.capital_fraction for rec in records}
        approvals = {rec.operator_approval_id.strip() for rec in records}
        checksums = {rec.config_checksum.strip() for rec in records}

        if len(starts) != 1 or len(ends) != 1:
            blockers.append(f"{prefix} has conflicting stage window metadata")
        if len(capital_fractions) != 1:
            blockers.append(f"{prefix} has conflicting capital-fraction metadata")
        elif abs(first.capital_fraction - expected.capital_fraction) > 0.000001:
            blockers.append(
                f"{prefix} capital fraction is {first.capital_fraction:.1%}; "
                f"expected {expected.capital_fraction:.0%}"
            )

        if previous_end is not None and first.stage_started_at <= previous_end:
            blockers.append(f"{prefix} starts before the previous stage ended")
        if first.stage_ended_at < first.stage_started_at:
            blockers.append(f"{prefix} ends before it starts")

        calendar_days = (first.stage_ended_at.date() - first.stage_started_at.date()).days + 1
        if calendar_days < self.policy.required_calendar_days_per_stage:
            blockers.append(
                f"{prefix} span is {calendar_days} calendar days; "
                f"requires at least {self.policy.required_calendar_days_per_stage}"
            )

        if _during_nse_market_hours(first.stage_started_at):
            blockers.append(f"{prefix} activation is recorded during NSE market hours")
        if _during_nse_market_hours(first.stage_ended_at):
            blockers.append(f"{prefix} completion is recorded during NSE market hours")

        if "" in approvals:
            blockers.append(f"{prefix} operator approval id is missing")
        if len(approvals) > 1:
            blockers.append(f"{prefix} has conflicting operator approval ids")
        if "" in checksums:
            blockers.append(f"{prefix} config checksum is missing")
        if len(checksums) > 1:
            blockers.append(f"{prefix} has conflicting config checksums")

        if any(rec.live_host_id != prerequisite.live_host_id for rec in records):
            blockers.append(f"{prefix} contains records from a different live host")
        if any(rec.governor_max_orders_per_sec <= 0 for rec in records):
            blockers.append(f"{prefix} governor max_orders_per_sec must be greater than 0")
        elif any(rec.governor_max_orders_per_sec > self.policy.max_orders_per_sec for rec in records):
            blockers.append(
                f"{prefix} governor max_orders_per_sec exceeds {self.policy.max_orders_per_sec:g}"
            )

        dates = sorted({rec.trading_date for rec in records})
        if len(dates) < self.policy.min_reviewed_trading_days_per_stage:
            blockers.append(
                f"{prefix} has only {len(dates)} reviewed trading days; "
                f"requires at least {self.policy.min_reviewed_trading_days_per_stage}"
            )
        if any(rec.trading_date < first.stage_started_at.date() for rec in records):
            blockers.append(f"{prefix} includes trading records before activation")
        if any(rec.trading_date > first.stage_ended_at.date() for rec in records):
            blockers.append(f"{prefix} includes trading records after stage completion")

        expected_sleeves = set(self.policy.expected_sleeves)
        by_date: dict[dt.date, set[str]] = {}
        for rec in records:
            by_date.setdefault(rec.trading_date, set()).add(rec.sleeve)
        for day, sleeves in sorted(by_date.items()):
            missing = sorted(expected_sleeves - sleeves)
            if missing:
                blockers.append(f"{prefix} {day.isoformat()} missing sleeve reviews: {', '.join(missing)}")

        return blockers


def _during_nse_market_hours(value: dt.datetime) -> bool:
    if value.weekday() >= 5:
        return False
    current = value.time()
    return dt.time(9, 15) <= current <= dt.time(15, 30)
