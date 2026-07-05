r"""
Executable specification for xenalgo.execution order state machine + journal.

Covers: SI-3 (positions change only on fills), SI-9 (restart never loses an
acknowledged order), SI-4 (idempotent fill application). Requirement FR-6, FR-16.

State machine (TRD §2.6/§3):
  INTENT -> SUBMITTED -> TRANSIT/PENDING -> PART_TRADED* -> TRADED
                      \-> REJECTED         \-> CANCELLED   \-> EXPIRED

Skips until xenalgo.execution exists (Phase 1).
"""
from __future__ import annotations

import pytest

execu = pytest.importorskip("xenalgo.execution")


LEGAL = {
    "INTENT": {"SUBMITTED", "REJECTED"},
    "SUBMITTED": {"TRANSIT", "PENDING", "REJECTED"},
    "TRANSIT": {"PENDING", "REJECTED"},
    "PENDING": {"PART_TRADED", "TRADED", "CANCELLED", "REJECTED", "EXPIRED"},
    "PART_TRADED": {"PART_TRADED", "TRADED", "CANCELLED", "EXPIRED"},
    "TRADED": set(),
    "REJECTED": set(),
    "CANCELLED": set(),
    "EXPIRED": set(),
}


def test_legal_transitions_accepted(tmp_journal):
    j = execu.Journal(tmp_journal)
    sm = execu.OrderStateMachine(j, correlation_id="cid-1")
    sm.to("SUBMITTED"); sm.to("PENDING"); sm.to("TRADED")
    assert sm.state == "TRADED"


@pytest.mark.parametrize("frm,to", [
    ("INTENT", "TRADED"),      # skipping submission
    ("TRADED", "PENDING"),     # terminal reopened
    ("REJECTED", "SUBMITTED"),
    ("CANCELLED", "TRADED"),
])
def test_illegal_transitions_rejected(tmp_journal, frm, to):
    j = execu.Journal(tmp_journal)
    sm = execu.OrderStateMachine(j, correlation_id="cid-2", state=frm)
    with pytest.raises(execu.IllegalTransition):
        sm.to(to)


# ── SI-3: positions mutate only on a confirmed fill ──────────────────────
def test_pending_does_not_change_positions(tmp_journal):
    book = execu.PositionBook(execu.Journal(tmp_journal))
    sm = execu.OrderStateMachine(book.journal, correlation_id="cid-3")
    sm.to("SUBMITTED"); sm.to("PENDING")
    book.apply_state(sm)
    assert book.qty("RELIANCE") == 0            # no fill yet -> no position


def test_confirmed_fill_changes_positions(tmp_journal):
    book = execu.PositionBook(execu.Journal(tmp_journal))
    fill = execu.Fill(correlation_id="cid-4", symbol="RELIANCE",
                      side="BUY", filled_qty=10, avg_price=1000.0)
    book.apply_fill(fill)
    assert book.qty("RELIANCE") == 10


# ── SI-4: applying the same fill twice is a no-op ────────────────────────
def test_duplicate_fill_is_idempotent(tmp_journal):
    book = execu.PositionBook(execu.Journal(tmp_journal))
    fill = execu.Fill(correlation_id="cid-5", symbol="TCS",
                      side="BUY", filled_qty=5, avg_price=3000.0,
                      broker_order_id="oid-5", event_key="oid-5:TRADED")
    book.apply_fill(fill)
    book.apply_fill(fill)                        # replayed / redundant channel
    assert book.qty("TCS") == 5


# ── SI-9: journal is append-only and replay == derived state ─────────────
def test_journal_is_append_only(tmp_journal):
    j = execu.Journal(tmp_journal)
    j.append(correlation_id="cid-6", state="INTENT", symbol="INFY",
             side="BUY", intended_qty=3, limit_price=1500.0)
    with pytest.raises(Exception):
        j.raw_execute("UPDATE order_events SET state='TRADED'")
    with pytest.raises(Exception):
        j.raw_execute("DELETE FROM order_events")


def test_replay_reconstructs_derived_state(tmp_journal):
    j = execu.Journal(tmp_journal)
    book = execu.PositionBook(j)
    book.apply_fill(execu.Fill("cid-7", "SBIN", "BUY", 20, 600.0))
    book.apply_fill(execu.Fill("cid-8", "SBIN", "SELL", 5, 620.0))
    # Fresh objects replay the same journal file:
    j2 = execu.Journal(tmp_journal)
    replayed = execu.PositionBook.from_replay(j2)
    assert replayed.qty("SBIN") == 15


# ── SI-9: crash mid-write leaves a consistent, replayable journal ────────
def test_partial_fill_accumulates(tmp_journal):
    book = execu.PositionBook(execu.Journal(tmp_journal))
    book.apply_fill(execu.Fill("cid-9", "ITC", "BUY", 4, 400.0, event_key="a"))
    book.apply_fill(execu.Fill("cid-9", "ITC", "BUY", 6, 401.0, event_key="b"))
    assert book.qty("ITC") == 10
