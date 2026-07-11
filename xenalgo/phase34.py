from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


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


def _as_optional_datetime(value: str | dt.datetime | None) -> dt.datetime | None:
    if value is None or value == "":
        return None
    return _as_datetime(value)


def _as_optional_date(value: str | dt.date | dt.datetime | None) -> dt.date | None:
    if value is None or value == "":
        return None
    return _as_date(value)


def _as_bool(value: str | bool | int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return value.strip().lower() in {"1", "true", "yes", "y", "ok", "pass", "passed"}


@dataclass(frozen=True)
class GoLiveChecklistEvidence:
    """Operator-supplied non-secret evidence for the Phase 3.4 go-live gate."""

    activated_at: dt.datetime
    live_host_id: str
    config_checksum: str
    phase0_foundation_passed: bool
    phase1_execution_core_passed: bool
    phase2_console_passed: bool
    phase31_failure_injection_passed: bool
    phase32_burn_in_passed: bool
    phase32_live_host_readiness_passed: bool
    phase33_post_migration_passed: bool
    static_ip_verified_at: dt.datetime | None
    token_refresh_sessions: int
    backup_restore_drill_at: dt.date | None
    local_kill_switch_verified_at: dt.datetime | None
    session_revocation_verified_at: dt.datetime | None
    phone_alerts_confirmed_at: dt.datetime | None
    dedicated_account_funded: bool
    operator_approval_id: str
    live_trading_enabled: bool
    broker_order_api_enabled: bool
    live_trading_mode: str
    capital_fraction: float
    governor_max_orders_per_sec: float

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "GoLiveChecklistEvidence":
        return cls(
            activated_at=_as_datetime(row["activated_at"]),
            live_host_id=row.get("live_host_id", ""),
            config_checksum=row.get("config_checksum", ""),
            phase0_foundation_passed=_as_bool(row.get("phase0_foundation_passed", "false")),
            phase1_execution_core_passed=_as_bool(row.get("phase1_execution_core_passed", "false")),
            phase2_console_passed=_as_bool(row.get("phase2_console_passed", "false")),
            phase31_failure_injection_passed=_as_bool(row.get("phase31_failure_injection_passed", "false")),
            phase32_burn_in_passed=_as_bool(row.get("phase32_burn_in_passed", "false")),
            phase32_live_host_readiness_passed=_as_bool(
                row.get("phase32_live_host_readiness_passed", "false")
            ),
            phase33_post_migration_passed=_as_bool(row.get("phase33_post_migration_passed", "false")),
            static_ip_verified_at=_as_optional_datetime(row.get("static_ip_verified_at")),
            token_refresh_sessions=int(row.get("token_refresh_sessions", "0") or 0),
            backup_restore_drill_at=_as_optional_date(row.get("backup_restore_drill_at")),
            local_kill_switch_verified_at=_as_optional_datetime(
                row.get("local_kill_switch_verified_at")
            ),
            session_revocation_verified_at=_as_optional_datetime(
                row.get("session_revocation_verified_at")
            ),
            phone_alerts_confirmed_at=_as_optional_datetime(row.get("phone_alerts_confirmed_at")),
            dedicated_account_funded=_as_bool(row.get("dedicated_account_funded", "false")),
            operator_approval_id=row.get("operator_approval_id", ""),
            live_trading_enabled=_as_bool(row.get("live_trading_enabled", "false")),
            broker_order_api_enabled=_as_bool(row.get("broker_order_api_enabled", "false")),
            live_trading_mode=row.get("live_trading_mode", ""),
            capital_fraction=float(row.get("capital_fraction", "0") or 0),
            governor_max_orders_per_sec=float(row.get("governor_max_orders_per_sec", "0") or 0),
        )


@dataclass(frozen=True)
class GoLiveChecklistReport:
    blockers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.blockers


def load_go_live_checklist_csv(path: str | Path) -> list[GoLiveChecklistEvidence]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [GoLiveChecklistEvidence.from_row(row) for row in csv.DictReader(fh)]


class GoLiveChecklistReview:
    """Evaluates the repository-verifiable evidence gate for Phase 3.4.

    This class validates evidence only. It does not call Fyers, mutate config, or enable
    order placement.
    """

    def __init__(
        self,
        *,
        max_initial_capital_fraction: float = 0.10,
        min_token_refresh_sessions: int = 5,
        max_orders_per_sec: float = 2.0,
    ) -> None:
        self.max_initial_capital_fraction = max_initial_capital_fraction
        self.min_token_refresh_sessions = min_token_refresh_sessions
        self.max_orders_per_sec = max_orders_per_sec

    def evaluate(
        self,
        evidence: GoLiveChecklistEvidence | Iterable[GoLiveChecklistEvidence],
        *,
        require_activation: bool = True,
    ) -> GoLiveChecklistReport:
        records = [evidence] if isinstance(evidence, GoLiveChecklistEvidence) else list(evidence)
        if len(records) != 1:
            return GoLiveChecklistReport((f"expected exactly one go-live checklist row; got {len(records)}",))
        return GoLiveChecklistReport(tuple(self._blockers(records[0], require_activation)))

    def _blockers(self, evidence: GoLiveChecklistEvidence, require_activation: bool) -> list[str]:
        blockers: list[str] = []

        required_flags = {
            "G0 foundation evidence has not passed": evidence.phase0_foundation_passed,
            "G1 execution-core evidence has not passed": evidence.phase1_execution_core_passed,
            "G2 console evidence has not passed": evidence.phase2_console_passed,
            "Phase 3.1 failure-injection evidence has not passed": evidence.phase31_failure_injection_passed,
            "Phase 3.2 burn-in evidence has not passed": evidence.phase32_burn_in_passed,
            "Phase 3.2 live-host readiness evidence has not passed": (
                evidence.phase32_live_host_readiness_passed
            ),
            "Phase 3.3 post-migration evidence has not passed": evidence.phase33_post_migration_passed,
        }
        blockers.extend(message for message, ok in required_flags.items() if not ok)

        if not evidence.live_host_id.strip():
            blockers.append("live host id is missing")
        if not evidence.config_checksum.strip():
            blockers.append("go-live config checksum is missing")

        if evidence.static_ip_verified_at is None:
            blockers.append("static IP startup verification evidence is missing")
        elif evidence.static_ip_verified_at > evidence.activated_at:
            blockers.append("static IP was verified after the go-live activation timestamp")

        if evidence.token_refresh_sessions < self.min_token_refresh_sessions:
            blockers.append(
                f"only {evidence.token_refresh_sessions} token-refresh sessions; "
                f"requires at least {self.min_token_refresh_sessions}"
            )

        activation_date = evidence.activated_at.date()
        if evidence.backup_restore_drill_at is None:
            blockers.append("successful live-host restore drill is not evidenced")
        elif evidence.backup_restore_drill_at > activation_date:
            blockers.append("restore drill is recorded after the go-live activation date")

        if evidence.local_kill_switch_verified_at is None:
            blockers.append("local kill-switch control-path verification is missing")
        elif evidence.local_kill_switch_verified_at > evidence.activated_at:
            blockers.append("local kill-switch control path was verified after go-live activation")
        if evidence.session_revocation_verified_at is None:
            blockers.append("Fyers session-revocation control verification is missing")
        elif evidence.session_revocation_verified_at > evidence.activated_at:
            blockers.append("Fyers session revocation was verified after go-live activation")

        if evidence.phone_alerts_confirmed_at is None:
            blockers.append("real-phone alert confirmation is missing")
        elif evidence.phone_alerts_confirmed_at > evidence.activated_at:
            blockers.append("real-phone alerts were confirmed after go-live activation")

        if not evidence.dedicated_account_funded:
            blockers.append("dedicated funded account is not evidenced")
        if not evidence.operator_approval_id.strip():
            blockers.append("explicit operator approval id is missing")

        if evidence.capital_fraction <= 0:
            blockers.append("initial live capital fraction must be greater than 0")
        elif evidence.capital_fraction > self.max_initial_capital_fraction:
            blockers.append(
                f"initial live capital fraction is {evidence.capital_fraction:.1%}; "
                f"Phase 3.4 allows at most {self.max_initial_capital_fraction:.0%}"
            )

        if evidence.governor_max_orders_per_sec <= 0:
            blockers.append("governor max_orders_per_sec must be greater than 0")
        elif evidence.governor_max_orders_per_sec > self.max_orders_per_sec:
            blockers.append(
                f"governor max_orders_per_sec is {evidence.governor_max_orders_per_sec:g}; "
                f"must stay at or below {self.max_orders_per_sec:g}"
            )

        if _during_nse_market_hours(evidence.activated_at):
            blockers.append("go-live activation is recorded during NSE market hours")

        mode = evidence.live_trading_mode.strip().lower()
        if require_activation:
            if mode != "live":
                blockers.append("live_trading.mode must be live for Phase 3.4 activation")
            if not evidence.live_trading_enabled:
                blockers.append("live_trading.enabled must be true for Phase 3.4 activation")
            if not evidence.broker_order_api_enabled:
                blockers.append("broker.order_api_enabled must be true for Phase 3.4 activation")
        else:
            if evidence.live_trading_enabled:
                blockers.append("live_trading.enabled must remain false during pre-activation review")
            if evidence.broker_order_api_enabled:
                blockers.append("broker.order_api_enabled must remain false during pre-activation review")
            if mode not in {"paper", "live"}:
                blockers.append("live_trading.mode must be paper or live")

        return blockers


def _during_nse_market_hours(value: dt.datetime) -> bool:
    if value.weekday() >= 5:
        return False
    current = value.time()
    return dt.time(9, 15) <= current <= dt.time(15, 30)
