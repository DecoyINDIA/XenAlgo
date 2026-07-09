from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from xenalgo.execution import Journal
from xenalgo.learning import AIProposalReviewer, LearningMemoryStore, StaticReviewClient, TradeJournalAnalytics
from xenalgo.web import ConsoleStore, create_app


def _seed_learning_journal(path: str) -> None:
    journal = Journal(path)
    ConsoleStore(path)
    journal.append(
        correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
        state="INTENT",
        sleeve="std30",
        symbol="RELIANCE",
        security_id="2885",
        side="BUY",
        intended_qty=10,
        limit_price=100.0,
    )
    journal.append(
        correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
        state="TRADED",
        sleeve="unknown",
        symbol="RELIANCE",
        security_id="2885",
        side="BUY",
        intended_qty=10,
        limit_price=100.0,
        filled_qty=10,
        avg_fill_price=101.0,
        raw_json={
            "event_key": "paper-1:TRADED",
            "model_price": 100.0,
            "expected_return_pct": 0.03,
            "realized_return_pct": 0.005,
            "regime": "volatile",
        },
    )
    with sqlite3.connect(path) as con:
        con.execute(
            """
            INSERT INTO portfolio_snapshots(
              ts_utc, equity, cash, positions_value, day_pnl, peak_equity
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("2026-07-01T10:00:00+00:00", 980000.0, 900000.0, 80000.0, -15000.0, 1000000.0),
        )


def _proposal() -> dict:
    return {
        "title": "Reduce std30 exposure after slippage review",
        "sleeve": "std30",
        "insight": "std30 underperformed expected return and paid elevated slippage.",
        "evidence": [{"metric": "edge_gap_pct", "value": -0.025}],
        "proposed_config": {"sleeves.std30.capital_fraction": 0.30},
        "risk_notes": "Proposal only; operator must approve before any config version is recorded.",
        "confidence": 0.72,
    }


def test_phase4_analytics_are_deterministic_and_sleeve_attributed(tmp_journal):
    """FR-20/SI-3: learning reads replayable fills only; sleeve attribution is recovered from intent."""
    _seed_learning_journal(tmp_journal)

    report = TradeJournalAnalytics(tmp_journal).build_report().as_dict()

    assert report["summary"]["fill_count"] == 1
    assert report["sleeves"]["std30"]["gross_notional"] == 1010.0
    assert report["sleeves"]["std30"]["avg_slippage_bps"] == 100.0
    assert report["alpha_decay"] == [
        {
            "sleeve": "std30",
            "sample_size": 1,
            "expected_return_pct": 0.03,
            "realized_return_pct": 0.005,
            "edge_gap_pct": -0.025,
            "status": "review",
        }
    ]
    assert report["regimes"][0]["tag"] == "adverse"


def test_phase4_memory_keeps_proposals_pending_until_explicit_approval(tmp_journal):
    """FR-20/SI-11: proposals are inert until an operator approves and audits a config version."""
    store = LearningMemoryStore(tmp_journal)
    proposal_id = store.add_proposal(_proposal())

    pending = store.pending_proposals()
    assert pending[0]["proposal_id"] == proposal_id
    assert pending[0]["status"] == "PENDING"

    with pytest.raises(ValueError, match="approved config snapshot"):
        store.approve_proposal(proposal_id, actor="operator", reason="reviewed", yaml_snapshot="")

    checksum = store.approve_proposal(
        proposal_id,
        actor="operator",
        reason="approved after paper review",
        yaml_snapshot="sleeves:\n  std30:\n    capital_fraction: 0.30\n",
    )

    approved = store.proposals()[0]
    assert approved["status"] == "APPROVED"
    assert approved["applied_config_checksum"] == checksum
    with sqlite3.connect(tmp_journal) as con:
        audit_actions = [
            row[0]
            for row in con.execute("SELECT action FROM audit_log ORDER BY ts_utc ASC").fetchall()
        ]
    assert "learning.proposal.create" in audit_actions
    assert "learning.proposal.approve" in audit_actions


def test_phase4_reviewer_accepts_only_strict_structured_proposals(tmp_journal):
    """FR-20: AI API output is schema-checked proposal text, not executable trading behavior."""
    _seed_learning_journal(tmp_journal)
    report = TradeJournalAnalytics(tmp_journal).build_report()

    proposal = AIProposalReviewer(StaticReviewClient(_proposal())).review(report)

    assert proposal.sleeve == "std30"
    assert proposal.proposed_config == {"sleeves.std30.capital_fraction": 0.30}

    bad = dict(_proposal(), confidence=2.0)
    with pytest.raises(ValueError, match="confidence"):
        AIProposalReviewer(StaticReviewClient(bad)).review(report)


def test_phase4_dashboard_proposal_review_requires_operator_token(tmp_journal):
    """FR-20/SI-11: dashboard approval is authenticated and writes an auditable config version."""
    proposal_id = LearningMemoryStore(tmp_journal).add_proposal(_proposal())
    store = ConsoleStore(tmp_journal)
    client = TestClient(create_app(store, control_token="secret"))

    learning = client.get("/api/learning")
    assert learning.status_code == 200
    assert learning.json()["pending_proposals"][0]["proposal_id"] == proposal_id

    assert (
        client.post(
            f"/learning/proposals/{proposal_id}/approve?actor=operator&reason=reviewed",
            content="sleeves:\n  std30:\n    capital_fraction: 0.30\n",
        ).status_code
        == 401
    )

    approved = client.post(
        f"/learning/proposals/{proposal_id}/approve?actor=operator&reason=reviewed",
        headers={"X-XenAlgo-Console-Token": "secret"},
        content="sleeves:\n  std30:\n    capital_fraction: 0.30\n",
    )

    assert approved.status_code == 200
    snapshot = client.get("/api/snapshot").json()
    assert snapshot["summary"]["pending_learning_proposals"] == 0
    assert snapshot["learning"]["proposals"][0]["status"] == "APPROVED"
