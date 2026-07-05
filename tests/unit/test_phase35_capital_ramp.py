"""
Executable specifications for Phase 3.5 staged capital-ramp evidence.

Covers: PRD G3/G4, TRD deployment and ops gates, G3 go-live criteria,
SI-5/SI-10/SI-12. No test touches the Dhan API or places a live order.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

phase35 = pytest.importorskip("xenalgo.phase35")


def _prerequisite(**overrides):
    values = dict(
        phase34_go_live_passed=True,
        live_host_id="aws-mumbai-live-1",
        initial_capital_fraction=0.10,
    )
    values.update(overrides)
    return phase35.RampPrerequisiteEvidence(**values)


def _clean_records() -> list[phase35.RampRecord]:
    records = []
    starts = [
        dt.datetime(2026, 8, 16, 8, 0),
        dt.datetime(2026, 8, 30, 8, 0),
        dt.datetime(2026, 9, 13, 8, 0),
        dt.datetime(2026, 9, 27, 8, 0),
    ]
    stages = [("10%", 0.10), ("25%", 0.25), ("50%", 0.50), ("100%", 1.00)]
    for (stage, fraction), started_at in zip(stages, starts):
        ended_at = started_at + dt.timedelta(days=13, hours=10)
        for offset in range(14):
            day = started_at.date() + dt.timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            for sleeve in phase35.DEFAULT_SLEEVES:
                records.append(
                    phase35.RampRecord(
                        stage=stage,
                        capital_fraction=fraction,
                        stage_started_at=started_at,
                        stage_ended_at=ended_at,
                        trading_date=day,
                        sleeve=sleeve,
                        live_return=0.010,
                        backtest_return=0.011,
                        live_host_id="aws-mumbai-live-1",
                        config_checksum=f"sha256:{stage}",
                        operator_approval_id=f"approval-{stage}",
                        governor_max_orders_per_sec=2,
                    )
                )
    return records


def test_capital_ramp_passes_after_four_clean_two_week_stages():
    summary = phase35.CapitalRampReview().evaluate(_clean_records(), _prerequisite())

    assert summary.passed is True
    assert summary.stages_reviewed == 4
    assert summary.total_records == 120
    assert summary.within_tolerance_ratio == 1.0


def test_capital_ramp_fails_closed_on_missing_or_unsafe_evidence():
    records = [
        phase35.RampRecord(
            stage="10%",
            capital_fraction=0.25,
            stage_started_at=dt.datetime(2026, 8, 17, 10, 0),
            stage_ended_at=dt.datetime(2026, 8, 17, 11, 0),
            trading_date=dt.date(2026, 8, 17),
            sleeve="std30",
            live_return=0.030,
            backtest_return=0.000,
            live_host_id="old-live-host",
            config_checksum="",
            operator_approval_id="",
            governor_max_orders_per_sec=3,
            safety_incidents=1,
            reconciliation_clean=False,
            broker_kill_switch_armed=False,
            unexplained_outlier=True,
        )
    ]

    summary = phase35.CapitalRampReview().evaluate(
        records,
        _prerequisite(
            phase34_go_live_passed=False,
            live_host_id="aws-mumbai-live-1",
            initial_capital_fraction=0.25,
        ),
    )

    assert summary.passed is False
    rendered = " | ".join(summary.blockers)
    assert "Phase 3.4 go-live" in rendered
    assert "start from the approved 10%" in rendered
    assert "expected ramp stages" in rendered
    assert "capital fraction is 25.0%" in rendered
    assert "calendar days" in rendered
    assert "activation is recorded during NSE market hours" in rendered
    assert "completion is recorded during NSE market hours" in rendered
    assert "operator approval id is missing" in rendered
    assert "config checksum is missing" in rendered
    assert "different live host" in rendered
    assert "governor max_orders_per_sec exceeds 2" in rendered
    assert "reviewed trading days" in rendered
    assert "missing sleeve reviews" in rendered
    assert "within tolerance" in rendered
    assert "safety incidents" in rendered
    assert "reconciliation checks" in rendered
    assert "kill switch" in rendered
    assert "unexplained ramp outliers" in rendered


def test_capital_ramp_requires_non_overlapping_stage_order():
    records = _clean_records()
    shifted = [
        (
            phase35.RampRecord(
                **{
                    **rec.__dict__,
                    "stage_started_at": dt.datetime(2026, 8, 20, 8, 0),
                }
            )
            if rec.stage == "25%"
            else rec
        )
        for rec in records
    ]

    summary = phase35.CapitalRampReview().evaluate(shifted, _prerequisite())

    assert summary.passed is False
    assert "25% stage starts before the previous stage ended" in " | ".join(summary.blockers)


def test_capital_ramp_csv_loader_reads_operator_evidence():
    evidence_dir = Path(".tmp") / "test_phase35_capital_ramp"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = evidence_dir / "phase35.csv"
    evidence.write_text(
        "stage,capital_fraction,stage_started_at,stage_ended_at,trading_date,sleeve,"
        "live_return,backtest_return,live_host_id,config_checksum,operator_approval_id,"
        "governor_max_orders_per_sec,safety_incidents,reconciliation_clean,"
        "broker_kill_switch_armed,unexplained_outlier,notes\n"
        "10%,0.10,2026-08-16T08:00:00,2026-08-29T18:00:00,2026-08-17,std30,"
        "0.010,0.011,aws-mumbai-live-1,sha256:10,approval-10,2,0,true,true,false,clean\n",
        encoding="utf-8",
    )

    records = phase35.load_ramp_csv(evidence)

    assert len(records) == 1
    assert records[0].stage == "10%"
    assert records[0].capital_fraction == 0.10
    assert records[0].within_tolerance(0.005) is True
