from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


class LearningMemoryStore:
    """SQLite-native memory for Phase 4 observations and proposal review."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init(self) -> None:
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_observations(
                  observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  created_utc TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_proposals(
                  proposal_id TEXT PRIMARY KEY,
                  created_utc TEXT NOT NULL,
                  status TEXT NOT NULL,
                  title TEXT NOT NULL,
                  sleeve TEXT NOT NULL,
                  insight TEXT NOT NULL,
                  evidence_json TEXT NOT NULL,
                  proposed_config_json TEXT NOT NULL,
                  risk_notes TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  source TEXT NOT NULL,
                  reviewed_utc TEXT,
                  reviewed_by TEXT,
                  review_reason TEXT,
                  applied_config_checksum TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS config_versions(
                  checksum TEXT PRIMARY KEY,
                  applied_utc TEXT NOT NULL,
                  yaml_snapshot TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log(
                  ts_utc TEXT NOT NULL,
                  actor TEXT NOT NULL,
                  action TEXT NOT NULL,
                  detail TEXT NOT NULL
                )
                """
            )

    def remember_observation(self, kind: str, payload: dict[str, Any]) -> int:
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            cur = con.execute(
                """
                INSERT INTO learning_observations(created_utc, kind, payload_json)
                VALUES (?, ?, ?)
                """,
                (now, kind, json.dumps(payload, sort_keys=True)),
            )
            self._audit(con, "system", "learning.observation.record", {"kind": kind}, now=now)
            return int(cur.lastrowid)

    def add_proposal(self, proposal: dict[str, Any], *, source: str = "ai-review") -> str:
        normalized = _validate_proposal(proposal)
        proposal_id = _proposal_id(normalized)
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO learning_proposals(
                  proposal_id, created_utc, status, title, sleeve, insight,
                  evidence_json, proposed_config_json, risk_notes, confidence, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    now,
                    PENDING,
                    normalized["title"],
                    normalized["sleeve"],
                    normalized["insight"],
                    json.dumps(normalized["evidence"], sort_keys=True),
                    json.dumps(normalized["proposed_config"], sort_keys=True),
                    normalized["risk_notes"],
                    float(normalized["confidence"]),
                    source,
                ),
            )
            self._audit(
                con,
                "system",
                "learning.proposal.create",
                {"proposal_id": proposal_id, "source": source},
                now=now,
            )
        return proposal_id

    def pending_proposals(self) -> list[dict[str, Any]]:
        return [
            proposal
            for proposal in self.proposals(limit=100)
            if proposal["status"] == PENDING
        ]

    def proposals(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT proposal_id, created_utc, status, title, sleeve, insight,
                       evidence_json, proposed_config_json, risk_notes, confidence,
                       source, reviewed_utc, reviewed_by, review_reason,
                       applied_config_checksum
                FROM learning_proposals
                ORDER BY created_utc DESC, proposal_id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_proposal_from_row(row) for row in rows]

    def approve_proposal(
        self,
        proposal_id: str,
        *,
        actor: str,
        reason: str,
        yaml_snapshot: str,
    ) -> str:
        if not actor:
            raise ValueError("actor is required")
        if not reason:
            raise ValueError("approval reason is required")
        if not yaml_snapshot.strip():
            raise ValueError("approved config snapshot is required")
        checksum = hashlib.sha256(yaml_snapshot.encode("utf-8")).hexdigest()
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            row = con.execute(
                "SELECT status FROM learning_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown proposal: {proposal_id}")
            if row["status"] != PENDING:
                raise ValueError(f"proposal is already {row['status']}")
            con.execute(
                """
                INSERT INTO config_versions(checksum, applied_utc, yaml_snapshot)
                VALUES (?, ?, ?)
                """,
                (checksum, now, yaml_snapshot),
            )
            con.execute(
                """
                UPDATE learning_proposals
                SET status=?, reviewed_utc=?, reviewed_by=?, review_reason=?,
                    applied_config_checksum=?
                WHERE proposal_id=?
                """,
                (APPROVED, now, actor, reason, checksum, proposal_id),
            )
            self._audit(
                con,
                actor,
                "learning.proposal.approve",
                {"proposal_id": proposal_id, "checksum": checksum, "reason": reason},
                now=now,
            )
        return checksum

    def reject_proposal(self, proposal_id: str, *, actor: str, reason: str) -> None:
        if not actor:
            raise ValueError("actor is required")
        if not reason:
            raise ValueError("rejection reason is required")
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            row = con.execute(
                "SELECT status FROM learning_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown proposal: {proposal_id}")
            if row["status"] != PENDING:
                raise ValueError(f"proposal is already {row['status']}")
            con.execute(
                """
                UPDATE learning_proposals
                SET status=?, reviewed_utc=?, reviewed_by=?, review_reason=?
                WHERE proposal_id=?
                """,
                (REJECTED, now, actor, reason, proposal_id),
            )
            self._audit(
                con,
                actor,
                "learning.proposal.reject",
                {"proposal_id": proposal_id, "reason": reason},
                now=now,
            )

    def _audit(
        self,
        con: sqlite3.Connection,
        actor: str,
        action: str,
        detail: dict[str, Any],
        *,
        now: str | None = None,
    ) -> None:
        con.execute(
            "INSERT INTO audit_log(ts_utc, actor, action, detail) VALUES (?, ?, ?, ?)",
            (
                now or dt.datetime.now(dt.UTC).isoformat(),
                actor or "operator",
                action,
                json.dumps(detail, sort_keys=True),
            ),
        )


def _validate_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be a mapping")
    required = {
        "title": str,
        "sleeve": str,
        "insight": str,
        "evidence": list,
        "proposed_config": dict,
        "risk_notes": str,
    }
    normalized: dict[str, Any] = {}
    for field, expected_type in required.items():
        value = proposal.get(field)
        if not isinstance(value, expected_type):
            raise ValueError(f"proposal.{field} must be {expected_type.__name__}")
        if expected_type is str and not value.strip():
            raise ValueError(f"proposal.{field} must not be empty")
        normalized[field] = value
    confidence = proposal.get("confidence")
    if not isinstance(confidence, int | float):
        raise ValueError("proposal.confidence must be numeric")
    if confidence < 0 or confidence > 1:
        raise ValueError("proposal.confidence must be in [0, 1]")
    normalized["confidence"] = float(confidence)
    return normalized


def _proposal_id(proposal: dict[str, Any]) -> str:
    raw = json.dumps(proposal, sort_keys=True)
    return "lp-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _proposal_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "proposal_id": row["proposal_id"],
        "created_utc": row["created_utc"],
        "status": row["status"],
        "title": row["title"],
        "sleeve": row["sleeve"],
        "insight": row["insight"],
        "evidence": json.loads(row["evidence_json"] or "[]"),
        "proposed_config": json.loads(row["proposed_config_json"] or "{}"),
        "risk_notes": row["risk_notes"],
        "confidence": float(row["confidence"]),
        "source": row["source"],
        "reviewed_utc": row["reviewed_utc"],
        "reviewed_by": row["reviewed_by"],
        "review_reason": row["review_reason"],
        "applied_config_checksum": row["applied_config_checksum"],
    }
