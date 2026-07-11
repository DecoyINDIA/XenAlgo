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

import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
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


def test_cumulative_partial_fills_do_not_overstate_position(tmp_journal):
    """SI-4: broker partial-fill quantities are cumulative, not per-event deltas."""
    journal = execu.Journal(tmp_journal)
    book = execu.PositionBook(journal)

    book.apply_fill(
        execu.Fill(
            correlation_id="cid-cumulative",
            broker_order_id="oid-cumulative",
            symbol="SBIN",
            side="BUY",
            filled_qty=4,
            avg_price=600.0,
            event_key="oid-cumulative:PART_TRADED:4",
            state="PART_TRADED",
        )
    )
    book.apply_fill(
        execu.Fill(
            correlation_id="cid-cumulative",
            broker_order_id="oid-cumulative",
            symbol="SBIN",
            side="BUY",
            filled_qty=10,
            avg_price=601.0,
            event_key="oid-cumulative:TRADED:10",
        )
    )
    book.apply_fill(
        execu.Fill(
            correlation_id="cid-cumulative",
            broker_order_id="oid-cumulative",
            symbol="SBIN",
            side="BUY",
            filled_qty=10,
            avg_price=601.0,
            event_key="oid-cumulative:TRADED:10-duplicate-channel",
        )
    )

    assert book.qty("SBIN") == 10
    assert book.qty_for("cid-cumulative") == 10
    replayed = execu.PositionBook.from_replay(journal)
    assert replayed.qty("SBIN") == 10
    assert replayed.qty_for("cid-cumulative") == 10


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
    book.apply_fill(execu.Fill("cid-9", "ITC", "BUY", 4, 400.0, event_key="a", state="PART_TRADED"))
    book.apply_fill(execu.Fill("cid-9", "ITC", "BUY", 10, 401.0, event_key="b"))
    assert book.qty("ITC") == 10


def test_journal_survives_abrupt_process_exit_and_replays(tmp_path):
    journal_path = tmp_path / "crash.sqlite"
    ready_path = tmp_path / "ready.txt"
    writer_path = tmp_path / "writer.py"
    writer_path.write_text(
        textwrap.dedent(
            f"""
            import os
            import sys
            import time
            from pathlib import Path

            sys.path.insert(0, {str(Path.cwd())!r})

            from xenalgo.execution import Fill, Journal, PositionBook

            journal = Journal({str(journal_path)!r})
            book = PositionBook(journal)
            for idx in range(50):
                book.apply_fill(
                    Fill(
                        correlation_id=f"cid-crash-{{idx}}",
                        symbol="RELIANCE",
                        side="BUY",
                        filled_qty=1,
                        avg_price=100.0,
                        event_key=f"fill-crash-{{idx}}",
                    )
                )
                if idx == 4:
                    Path({str(ready_path)!r}).write_text("ready", encoding="utf-8")
                time.sleep(0.01)
            os._exit(9)
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen([sys.executable, str(writer_path)], cwd=Path.cwd())
    try:
        deadline = time.monotonic() + 10
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready_path.exists(), "child process did not commit the initial journal events"
        proc.kill()
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    with sqlite3.connect(journal_path) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        traded_rows = con.execute(
            "SELECT COUNT(*) FROM order_events WHERE state='TRADED'"
        ).fetchone()[0]

    replayed = execu.PositionBook.from_replay(execu.Journal(journal_path))
    assert traded_rows >= 5
    assert replayed.qty("RELIANCE") == traded_rows


NON_FILL_STATES = [state for state in LEGAL if state not in {"PART_TRADED", "TRADED"}]
SYMBOLS = ["RELIANCE", "TCS", "INFY", "SBIN", "ITC"]


@pytest.mark.property
@settings(max_examples=25, deadline=None)
@given(
    events=st.lists(
        st.tuples(
            st.sampled_from(NON_FILL_STATES),
            st.sampled_from(SYMBOLS),
            st.sampled_from(["BUY", "SELL"]),
            st.integers(min_value=0, max_value=500),
        ),
        min_size=1,
        max_size=12,
    )
)
def test_property_non_fill_events_never_replay_into_positions(events):
    """SI-3: even malformed non-fill journal events cannot mutate positions on replay."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal = execu.Journal(Path(tmpdir) / "journal.sqlite")
        for idx, (state, symbol, side, filled_qty) in enumerate(events):
            journal.append(
                correlation_id=f"cid-non-fill-{idx}",
                state=state,
                symbol=symbol,
                side=side,
                intended_qty=max(filled_qty, 1),
                filled_qty=filled_qty,
                avg_fill_price=100.0 if filled_qty else None,
            )

        replayed = execu.PositionBook.from_replay(journal)

        for symbol in SYMBOLS:
            assert replayed.qty(symbol) == 0


@pytest.mark.property
@settings(max_examples=25, deadline=None)
@given(
    fills=st.lists(
        st.tuples(
            st.text(alphabet="abcdef0123456789", min_size=1, max_size=8),
            st.sampled_from(SYMBOLS),
            st.sampled_from(["BUY", "SELL"]),
            st.integers(min_value=1, max_value=500),
        ),
        min_size=1,
        max_size=12,
    )
)
def test_property_duplicate_fill_event_keys_apply_once(fills):
    """SI-4: duplicate fill events from redundant channels are idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        journal = execu.Journal(Path(tmpdir) / "journal.sqlite")
        book = execu.PositionBook(journal)
        expected: dict[str, int] = {}
        seen: set[str] = set()

        for event_key, symbol, side, qty in fills:
            book.apply_fill(
                execu.Fill(
                    correlation_id=f"cid-fill-{event_key}",
                    symbol=symbol,
                    side=side,
                    filled_qty=qty,
                    avg_price=100.0,
                    event_key=event_key,
                )
            )
            if event_key in seen:
                continue
            seen.add(event_key)
            sign = 1 if side == "BUY" else -1
            expected[symbol] = expected.get(symbol, 0) + sign * qty

        for symbol in SYMBOLS:
            assert book.qty(symbol) == expected.get(symbol, 0)
