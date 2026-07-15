from __future__ import annotations

import pytest

from xenalgo.broker.governor import OrderGovernor
from xenalgo.execution import ExecutionEngine, Fill, FillListener, IllegalTransition, Journal, OrderStateMachine, PositionBook
from xenalgo.risk import RiskContext, RiskEngine


class ManualClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t


def _order(cid: str, *, qty: int = 1) -> dict:
    return {
        "correlation_id": cid,
        "sleeve": "std30",
        "symbol": "INFY",
        "security_id": "1594",
        "side": "BUY",
        "qty": qty,
        "limit_price": 1500.0,
    }


def test_order_records_submitted_before_pending(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    engine = ExecutionEngine(broker=mock_broker, journal=journal)

    result = engine.submit(**_order("xa-submitted-1"))

    assert result.state == "PENDING"
    assert [event["state"] for event in journal.events()] == ["INTENT", "SUBMITTED", "PENDING"]


def test_illegal_transition_raises(tmp_journal):
    sm = OrderStateMachine(Journal(tmp_journal), "xa-illegal-1")

    with pytest.raises(IllegalTransition):
        sm.to("PENDING")


def test_rejection_storm_halts_within_day_and_persists(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    engine = ExecutionEngine(
        broker=mock_broker,
        journal=journal,
        consecutive_failure_halt=3,
    )

    for i in range(3):
        mock_broker.reject_next = True
        assert engine.submit(**_order(f"xa-storm-{i}")).state == "REJECTED"

    result = engine.submit(**_order("xa-storm-3"))
    assert result.state == "REJECTED"
    assert result.reason == "halted"

    restarted = ExecutionEngine(
        broker=mock_broker,
        journal=Journal(tmp_journal),
        consecutive_failure_halt=3,
    )
    restarted_result = restarted.submit(**_order("xa-storm-after-restart"))
    assert restarted.is_halted() is True
    assert restarted_result.reason == "halted"


def test_governor_blocks_burst_end_to_end(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    clock = ManualClock()
    governor = OrderGovernor(max_per_sec=2, max_per_day=500, clock=clock.monotonic)
    engine = ExecutionEngine(broker=mock_broker, journal=journal, governor=governor)

    results = [engine.submit(**_order(f"xa-burst-{i}")) for i in range(100)]

    assert sum(1 for result in results if result.state == "PENDING") <= 2
    assert sum(1 for result in results if result.reason == "rate limited") >= 98
    assert len(mock_broker._orders) <= 2


def test_execution_engine_submits_scaled_risk_quantity(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    risk = RiskEngine(
        {
            "max_order_notional_inr": 10_000_000,
            "max_pct_of_adv": 0.05,
            "price_collar_pct": 0.03,
            "max_position_pct": 1.0,
            "fee_buffer_pct": 0.0,
        }
    )
    ctx = RiskContext(
        portfolio_value=10_000_000,
        positions={},
        adv={"INFY": 100},
        prev_close={"INFY": 1500.0},
        cash=10_000_000,
    )
    class RecordingBroker:
        def __init__(self):
            self.request = None

        def get_order_by_correlation(self, cid):
            return None

        def place_order(self, req):
            self.request = req
            return type(
                "Ack",
                (),
                {
                    "status": "PENDING",
                    "broker_order_id": "scaled-1",
                    "reason": "",
                },
            )()

    broker = RecordingBroker()
    engine = ExecutionEngine(broker=broker, journal=journal, risk_engine=risk, risk_context=ctx)

    result = engine.submit(**_order("xa-scaled-risk", qty=10))

    assert result.state == "PENDING"
    assert broker.request.qty == 5


def test_journal_raw_execute_allows_non_order_event_reads(tmp_journal):
    journal = Journal(tmp_journal)

    journal.raw_execute("SELECT 1")


def test_replay_skips_duplicate_raw_event_keys(tmp_journal):
    journal = Journal(tmp_journal)
    book = PositionBook(journal)
    fill = Fill(
        correlation_id="cid-dup-replay",
        broker_order_id="oid-dup-replay",
        symbol="INFY",
        side="BUY",
        filled_qty=5,
        avg_price=1500.0,
        event_key="same-event",
    )
    book.apply_fill(fill)
    journal.append(
        correlation_id="cid-dup-replay",
        broker_order_id="oid-dup-replay",
        state="TRADED",
        symbol="INFY",
        side="BUY",
        intended_qty=5,
        filled_qty=5,
        avg_fill_price=1500.0,
        raw_json={"event_key": "same-event"},
    )

    assert PositionBook.from_replay(journal).qty("INFY") == 5


def test_invalid_persisted_failure_count_loads_as_zero(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    journal.risk_state_set("consecutive_failures", "not-an-int")

    engine = ExecutionEngine(broker=mock_broker, journal=journal)

    assert engine.is_halted() is False


def test_poll_stuck_orders_ignores_missing_or_non_terminal_orders(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    listener = FillListener(mock_broker, journal)
    mock_broker.place_order(type("Req", (), _order("cid-pending"))())

    listener.poll_stuck_orders(["missing", "cid-pending"])

    assert listener.book.qty("INFY") == 0


def test_apply_fill_atomic_deduplication(tmp_journal):
    journal = Journal(tmp_journal)
    book = PositionBook(journal)
    
    fill = Fill(
        correlation_id="cid-atomic",
        symbol="INFY",
        side="BUY",
        filled_qty=5,
        avg_price=1500.0,
        broker_order_id="broker-1",
        event_key="unique-event-key"
    )
    
    book.apply_fill(fill)
    assert book.qty("INFY") == 5
    
    book.apply_fill(fill)
    assert book.qty("INFY") == 5
    
    events = [e for e in journal.events() if e["state"] == "TRADED"]
    assert len(events) == 1


def test_console_rearm_execution_halt(tmp_journal):
    from xenalgo.web.state import ConsoleStore
    store = ConsoleStore(tmp_journal)
    
    store.set_breaker("execution_halted", "true")
    
    # Wait: consecutive_failures is not in REARMABLE_BREAKERS so set_breaker will raise ValueError if called directly.
    # But wait, how does risk engine record consecutive_failures?
    # It does risk_state_set("consecutive_failures", str(val)).
    # Let's insert it into database directly or use risk_state_set via journal.
    journal = Journal(tmp_journal)
    journal.risk_state_set("consecutive_failures", "3")
    
    snap = store.snapshot()
    # active_breakers count should only count execution_halted, not consecutive_failures.
    assert snap["summary"]["active_breakers"] == 1
    
    store.rearm("execution_halted")
    snap_after = store.snapshot()
    assert snap_after["summary"]["active_breakers"] == 0
    assert next((r for r in snap_after["risk_state"] if r["key"] == "consecutive_failures"), None) is None


def test_risk_veto_does_not_increment_consecutive_failures(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    risk = RiskEngine({"max_order_notional_inr": 1})
    engine = ExecutionEngine(
        broker=mock_broker,
        journal=journal,
        risk_engine=risk,
        consecutive_failure_halt=3,
    )
    
    for i in range(3):
        assert engine.submit(**_order(f"xa-veto-{i}")).state == "REJECTED"
        
    assert journal.risk_state_get("consecutive_failures") is None
    assert engine.is_halted() is False


def test_poll_stuck_orders_recovers_partial_fills(mock_broker, tmp_journal):
    journal = Journal(tmp_journal)
    listener = FillListener(mock_broker, journal)
    
    order_data = _order("cid-partial", qty=10)
    mock_broker.place_order(type("Req", (), order_data)())
    
    mock_broker._orders["cid-partial"].update(
        state="PART_TRADED",
        filled_qty=5,
        avg_price=1500.0,
        symbol="INFY",
        side="BUY",
    )
    
    listener.poll_stuck_orders(["cid-partial"])
    assert listener.book.qty("INFY") == 5
    
    mock_broker._orders["cid-partial"].update(
        state="TRADED",
        filled_qty=10,
        avg_price=1500.0,
        symbol="INFY",
        side="BUY",
    )
    
    listener.poll_stuck_orders(["cid-partial"])
    assert listener.book.qty("INFY") == 10
    
    mock_broker._orders["cid-partial"].update(
        state="TRADED",
        filled_qty=10,
        avg_price=0.0,
        symbol="INFY",
        side="BUY",
    )
    listener.poll_stuck_orders(["cid-partial"])
    assert listener.book.qty("INFY") == 10




