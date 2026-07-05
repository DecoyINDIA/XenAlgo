from __future__ import annotations

import datetime as dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xenalgo.risk import OrderRequest, RiskContext, RiskDecision, RiskEngine


LEGAL_TRANSITIONS = {
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


class IllegalTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class Fill:
    correlation_id: str
    symbol: str
    side: str
    filled_qty: int
    avg_price: float
    broker_order_id: str | None = None
    event_key: str | None = None


@dataclass(frozen=True)
class SubmissionResult:
    state: str
    broker_order_id: str | None
    correlation_id: str
    reason: str = ""


class Journal:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._init()

    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS order_events(
                  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts_utc TEXT NOT NULL,
                  correlation_id TEXT NOT NULL,
                  broker_order_id TEXT,
                  sleeve TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  security_id TEXT NOT NULL,
                  side TEXT NOT NULL,
                  intended_qty INTEGER NOT NULL,
                  limit_price REAL,
                  state TEXT NOT NULL,
                  filled_qty INTEGER DEFAULT 0,
                  avg_fill_price REAL,
                  reason TEXT,
                  raw_json TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS orders(
                  correlation_id TEXT PRIMARY KEY,
                  broker_order_id TEXT,
                  state TEXT,
                  filled_qty INTEGER,
                  avg_fill_price REAL,
                  updated_utc TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS positions(
                  symbol TEXT PRIMARY KEY,
                  qty INTEGER NOT NULL,
                  avg_price REAL,
                  sleeve TEXT,
                  entry_date TEXT,
                  updated_utc TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS applied_events(
                  event_key TEXT PRIMARY KEY,
                  correlation_id TEXT NOT NULL,
                  applied_utc TEXT NOT NULL
                )
                """
            )

    def append(
        self,
        *,
        correlation_id: str,
        state: str,
        symbol: str = "UNKNOWN",
        side: str = "BUY",
        intended_qty: int = 0,
        limit_price: float | None = None,
        broker_order_id: str | None = None,
        sleeve: str = "unknown",
        security_id: str = "unknown",
        filled_qty: int = 0,
        avg_fill_price: float | None = None,
        reason: str | None = None,
        raw_json: dict[str, Any] | None = None,
    ) -> None:
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO order_events(
                  ts_utc, correlation_id, broker_order_id, sleeve, symbol,
                  security_id, side, intended_qty, limit_price, state,
                  filled_qty, avg_fill_price, reason, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    correlation_id,
                    broker_order_id,
                    sleeve,
                    symbol,
                    security_id,
                    side,
                    int(intended_qty),
                    limit_price,
                    state,
                    int(filled_qty),
                    avg_fill_price,
                    reason,
                    json.dumps(raw_json or {}, sort_keys=True),
                ),
            )
            con.execute(
                """
                INSERT INTO orders(correlation_id, broker_order_id, state, filled_qty, avg_fill_price, updated_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(correlation_id) DO UPDATE SET
                  broker_order_id=COALESCE(excluded.broker_order_id, orders.broker_order_id),
                  state=excluded.state,
                  filled_qty=excluded.filled_qty,
                  avg_fill_price=excluded.avg_fill_price,
                  updated_utc=excluded.updated_utc
                """,
                (
                    correlation_id,
                    broker_order_id,
                    state,
                    int(filled_qty),
                    avg_fill_price,
                    now,
                ),
            )

    def raw_execute(self, sql: str) -> None:
        verb = sql.strip().split(None, 1)[0].upper()
        if verb in {"UPDATE", "DELETE"} and "ORDER_EVENTS" in sql.upper():
            raise RuntimeError("order_events is append-only")
        with self._connect() as con:
            con.execute(sql)

    def events(self) -> list[sqlite3.Row]:
        with self._connect() as con:
            return list(con.execute("SELECT * FROM order_events ORDER BY event_id"))

    def has_correlation(self, correlation_id: str) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT 1 FROM order_events WHERE correlation_id=? LIMIT 1",
                (correlation_id,),
            ).fetchone()
        return row is not None

    def mark_applied(self, event_key: str, correlation_id: str) -> bool:
        try:
            with self._connect() as con:
                con.execute(
                    "INSERT INTO applied_events(event_key, correlation_id, applied_utc) VALUES (?, ?, ?)",
                    (event_key, correlation_id, dt.datetime.now(dt.UTC).isoformat()),
                )
            return True
        except sqlite3.IntegrityError:
            return False


class OrderStateMachine:
    def __init__(
        self,
        journal: Journal,
        correlation_id: str,
        state: str = "INTENT",
    ) -> None:
        self.journal = journal
        self.correlation_id = correlation_id
        self.state = state
        if state == "INTENT" and not self.journal.has_correlation(correlation_id):
            self.journal.append(correlation_id=correlation_id, state="INTENT")

    def to(self, state: str) -> None:
        if state not in LEGAL_TRANSITIONS.get(self.state, set()):
            raise IllegalTransition(f"illegal transition {self.state}->{state}")
        self.state = state
        self.journal.append(correlation_id=self.correlation_id, state=state)


class PositionBook:
    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self._qty: dict[str, int] = {}
        self._qty_by_cid: dict[str, int] = {}

    def apply_state(self, sm: OrderStateMachine) -> None:
        return None

    def apply_fill(self, fill: Fill) -> None:
        event_key = fill.event_key or f"{fill.correlation_id}:{fill.filled_qty}:{fill.avg_price}"
        if not self.journal.mark_applied(event_key, fill.correlation_id):
            return
        sign = 1 if fill.side.upper() == "BUY" else -1
        delta = sign * int(fill.filled_qty)
        self._qty[fill.symbol] = self._qty.get(fill.symbol, 0) + delta
        self._qty_by_cid[fill.correlation_id] = self._qty_by_cid.get(fill.correlation_id, 0) + delta
        self.journal.append(
            correlation_id=fill.correlation_id,
            broker_order_id=fill.broker_order_id,
            state="TRADED",
            symbol=fill.symbol,
            side=fill.side,
            intended_qty=fill.filled_qty,
            filled_qty=fill.filled_qty,
            avg_fill_price=fill.avg_price,
            raw_json={"event_key": event_key},
        )

    def qty(self, symbol: str) -> int:
        return self._qty.get(symbol, 0)

    def qty_for(self, correlation_id: str) -> int:
        return self._qty_by_cid.get(correlation_id, 0)

    @classmethod
    def from_replay(cls, journal: Journal) -> "PositionBook":
        book = cls(journal)
        seen: set[str] = set()
        for event in journal.events():
            if event["state"] != "TRADED" or not event["filled_qty"]:
                continue
            raw = json.loads(event["raw_json"] or "{}")
            event_key = raw.get("event_key") or f"{event['event_id']}"
            if event_key in seen:
                continue
            seen.add(event_key)
            sign = 1 if event["side"].upper() == "BUY" else -1
            delta = sign * int(event["filled_qty"])
            book._qty[event["symbol"]] = book._qty.get(event["symbol"], 0) + delta
            book._qty_by_cid[event["correlation_id"]] = (
                book._qty_by_cid.get(event["correlation_id"], 0) + delta
            )
        return book


class ExecutionEngine:
    def __init__(
        self,
        broker,
        journal: Journal,
        kill_switch=None,
        consecutive_failure_halt: int = 3,
        risk_engine: RiskEngine | None = None,
        risk_context: RiskContext | None = None,
    ) -> None:
        self.broker = broker
        self.journal = journal
        self.kill_switch = kill_switch
        self.consecutive_failure_halt = consecutive_failure_halt
        self.risk_engine = risk_engine or RiskEngine(
            {
                "max_order_notional_inr": 10_000_000_000,
                "max_pct_of_adv": 0.05,
                "price_collar_pct": 0.03,
                "max_position_pct": 1.0,
                "fee_buffer_pct": 0.0,
            }
        )
        self.risk_context = risk_context
        self._failures = 0
        self._halted = False

    def submit(self, **kwargs) -> SubmissionResult:
        if self._halted or (self.kill_switch and not self.kill_switch.allow_submission()):
            return SubmissionResult("REJECTED", None, kwargs["correlation_id"], "halted")

        cid = kwargs["correlation_id"]
        existing = self.broker.get_order_by_correlation(cid)
        if existing:
            return SubmissionResult(existing.get("state", "PENDING"), existing.get("broker_order_id"), cid)

        risk_order = OrderRequest(
            correlation_id=cid,
            sleeve=kwargs.get("sleeve", "unknown"),
            symbol=kwargs["symbol"],
            security_id=kwargs["security_id"],
            side=kwargs["side"],
            qty=int(kwargs["qty"]),
            limit_price=float(kwargs["limit_price"]),
        )
        risk_ctx = self.risk_context or _default_risk_context(risk_order)
        decision, allowed_qty, reason = self.risk_engine.check(risk_order, risk_ctx)
        if decision is RiskDecision.REJECT:
            self.journal.append(state="REJECTED", reason=reason, **_journal_fields(kwargs))
            self._failures += 1
            if self._failures >= self.consecutive_failure_halt:
                self._halted = True
            return SubmissionResult("REJECTED", None, cid, reason)
        if decision is RiskDecision.SCALE:
            kwargs = dict(kwargs, qty=allowed_qty)

        if not self.journal.has_correlation(cid):
            self.journal.append(state="INTENT", **_journal_fields(kwargs))

        ack = self.broker.place_order(_Request(**kwargs))
        state = "REJECTED" if ack.status == "REJECTED" else "PENDING"
        self.journal.append(
            state=state,
            broker_order_id=ack.broker_order_id,
            reason=getattr(ack, "reason", ""),
            **_journal_fields(kwargs),
        )
        if state == "REJECTED":
            self._failures += 1
            if self._failures >= self.consecutive_failure_halt:
                self._halted = True
        else:
            self._failures = 0
        return SubmissionResult(state, ack.broker_order_id, cid, getattr(ack, "reason", ""))

    def is_halted(self) -> bool:
        return self._halted


class FillListener:
    def __init__(self, broker, journal: Journal) -> None:
        self.broker = broker
        self.journal = journal
        self.book = PositionBook(journal)
        self.ws_down = False

    def simulate_ws_drop(self) -> None:
        self.ws_down = True

    def poll_stuck_orders(self, correlation_ids: list[str]) -> None:
        for cid in correlation_ids:
            order = self.broker.get_order_by_correlation(cid)
            if not order or order.get("state") != "TRADED":
                continue
            self.on_fill(
                Fill(
                    correlation_id=cid,
                    symbol=order.get("symbol", cid),
                    side=order.get("side", "BUY"),
                    filled_qty=int(order.get("filled_qty", 0)),
                    avg_price=float(order.get("avg_price", 0.0)),
                    broker_order_id=order.get("broker_order_id"),
                    event_key=f"{order.get('broker_order_id')}:{order.get('state')}",
                )
            )

    def on_fill(self, fill: Fill) -> None:
        self.book.apply_fill(fill)


class _Request:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def _journal_fields(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "correlation_id": values["correlation_id"],
        "sleeve": values.get("sleeve", "unknown"),
        "symbol": values.get("symbol", "UNKNOWN"),
        "security_id": values.get("security_id", "unknown"),
        "side": values.get("side", "BUY"),
        "intended_qty": values.get("intended_qty", values.get("qty", 0)),
        "limit_price": values.get("limit_price"),
    }


def _default_risk_context(order: OrderRequest) -> RiskContext:
    return RiskContext(
        portfolio_value=10_000_000_000.0,
        positions={},
        adv={order.symbol: max(order.qty * 100, 1_000_000)},
        prev_close={order.symbol: order.limit_price},
        cash=10_000_000_000.0,
        restricted=set(),
        seen_correlation_ids=set(),
        breakers={},
    )
