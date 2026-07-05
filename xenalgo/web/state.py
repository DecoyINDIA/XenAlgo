from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from xenalgo.config import load_config


REARMABLE_BREAKERS = {
    "kill_switch",
    "drawdown_halt",
    "daily_loss_halt",
    "stale_data",
    "reconciliation_mismatch",
    "consecutive_failures",
}


class ConsoleStore:
    """Read paper/live state for Phase 2 console views and audit operator controls."""

    def __init__(self, journal_path: str | Path) -> None:
        self.journal_path = str(journal_path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.journal_path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._connect() as con:
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
                CREATE TABLE IF NOT EXISTS risk_state(
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  updated_utc TEXT NOT NULL
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
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_snapshots(
                  ts_utc TEXT PRIMARY KEY,
                  equity REAL,
                  cash REAL,
                  positions_value REAL,
                  day_pnl REAL,
                  peak_equity REAL
                )
                """
            )

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as con:
            orders = _fetch_all(
                con,
                """
                SELECT correlation_id, broker_order_id, state, filled_qty,
                       avg_fill_price, updated_utc
                FROM orders
                ORDER BY updated_utc DESC, correlation_id DESC
                LIMIT 100
                """,
            )
            events = _fetch_all(
                con,
                """
                SELECT event_id, ts_utc, correlation_id, broker_order_id, sleeve,
                       symbol, side, intended_qty, limit_price, state, filled_qty,
                       avg_fill_price, reason
                FROM order_events
                ORDER BY event_id DESC
                LIMIT 100
                """,
            )
            risk_state = _fetch_all(
                con,
                "SELECT key, value, updated_utc FROM risk_state ORDER BY key",
            )
            audit = _fetch_all(
                con,
                """
                SELECT ts_utc, actor, action, detail
                FROM audit_log
                ORDER BY ts_utc DESC
                LIMIT 100
                """,
            )
            portfolio = _fetch_all(
                con,
                """
                SELECT ts_utc, equity, cash, positions_value, day_pnl, peak_equity
                FROM portfolio_snapshots
                ORDER BY ts_utc DESC
                LIMIT 20
                """,
            )
            positions = self._positions_from_events(con)

        return {
            "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
            "orders": orders,
            "positions": positions,
            "risk_state": risk_state,
            "portfolio": portfolio,
            "recent_events": events,
            "audit": audit,
            "summary": {
                "open_orders": sum(1 for order in orders if order["state"] not in _TERMINAL_STATES),
                "positions": len(positions),
                "active_breakers": len(risk_state),
                "events": len(events),
            },
        }

    def activate_kill(self, source: str = "dashboard", actor: str = "operator") -> None:
        now = dt.datetime.now(dt.UTC).isoformat()
        detail = json.dumps({"source": source or "dashboard"}, sort_keys=True)
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO risk_state(key, value, updated_utc)
                VALUES (?, ?, ?)
                """,
                ("kill_switch", source or "dashboard", now),
            )
            self._audit(con, actor, "kill_switch.activate", detail, now=now)

    def set_breaker(self, key: str, value: str = "active", actor: str = "system") -> None:
        if key not in REARMABLE_BREAKERS:
            raise ValueError(f"unsupported breaker: {key}")
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO risk_state(key, value, updated_utc)
                VALUES (?, ?, ?)
                """,
                (key, value, now),
            )
            self._audit(
                con,
                actor,
                "breaker.set",
                json.dumps({"key": key, "value": value}, sort_keys=True),
                now=now,
            )

    def rearm(self, key: str, actor: str = "operator", reason: str = "") -> None:
        if key not in REARMABLE_BREAKERS:
            raise ValueError(f"unsupported breaker: {key}")
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as con:
            con.execute("DELETE FROM risk_state WHERE key=?", (key,))
            self._audit(
                con,
                actor,
                "breaker.rearm",
                json.dumps({"key": key, "reason": reason}, sort_keys=True),
                now=now,
            )

    def record_postback(self, payload: dict[str, Any], actor: str = "dhan-postback") -> None:
        safe_payload = {
            "correlation_id": payload.get("correlationId") or payload.get("correlation_id"),
            "order_id": payload.get("orderId") or payload.get("order_id"),
            "status": payload.get("orderStatus") or payload.get("status"),
        }
        with self._connect() as con:
            self._audit(
                con,
                actor,
                "postback.enqueue",
                json.dumps(safe_payload, sort_keys=True),
            )

    def config_summary(self, profile: str = "live", root: str | Path | None = None) -> dict[str, Any]:
        config = load_config(profile, root)
        live = config.data.get("live_trading", {})
        broker = config.data.get("broker", {})
        web = config.data.get("web", {})
        return {
            "profile": config.profile,
            "path": str(config.path),
            "checksum": config.checksum,
            "live_trading_enabled": live.get("enabled"),
            "mode": live.get("mode"),
            "broker_order_api_enabled": broker.get("order_api_enabled"),
            "web": web,
        }

    def _positions_from_events(self, con: sqlite3.Connection) -> list[dict[str, Any]]:
        sleeve_by_cid = {
            row["correlation_id"]: row["sleeve"]
            for row in con.execute(
                """
                SELECT correlation_id, sleeve
                FROM order_events
                WHERE sleeve IS NOT NULL AND sleeve != 'unknown'
                ORDER BY event_id ASC
                """
            ).fetchall()
        }
        rows = con.execute(
            """
            SELECT event_id, correlation_id, ts_utc, sleeve, symbol, side,
                   filled_qty, avg_fill_price, raw_json
            FROM order_events
            WHERE state='TRADED' AND filled_qty > 0
            ORDER BY event_id ASC
            """
        ).fetchall()
        seen: set[str] = set()
        positions: dict[str, dict[str, Any]] = {}
        for row in rows:
            raw = json.loads(row["raw_json"] or "{}")
            event_key = raw.get("event_key") or str(row["event_id"])
            if event_key in seen:
                continue
            seen.add(event_key)
            qty = int(row["filled_qty"])
            sign = 1 if str(row["side"]).upper() == "BUY" else -1
            symbol = str(row["symbol"])
            current = positions.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "qty": 0,
                    "avg_price": 0.0,
                    "sleeves": set(),
                    "updated_utc": row["ts_utc"],
                },
            )
            current["qty"] += sign * qty
            current["avg_price"] = float(row["avg_fill_price"] or current["avg_price"] or 0.0)
            current["updated_utc"] = row["ts_utc"]
            current["sleeves"].add(sleeve_by_cid.get(row["correlation_id"], row["sleeve"]))

        result = []
        for position in positions.values():
            if position["qty"] == 0:
                continue
            position["sleeves"] = sorted(position["sleeves"])
            result.append(position)
        return sorted(result, key=lambda item: item["symbol"])

    def _audit(
        self,
        con: sqlite3.Connection,
        actor: str,
        action: str,
        detail: str,
        *,
        now: str | None = None,
    ) -> None:
        con.execute(
            "INSERT INTO audit_log(ts_utc, actor, action, detail) VALUES (?, ?, ?, ?)",
            (now or dt.datetime.now(dt.UTC).isoformat(), actor or "operator", action, detail),
        )


_TERMINAL_STATES = {"TRADED", "REJECTED", "CANCELLED", "EXPIRED"}


def _fetch_all(con: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in con.execute(sql).fetchall()]
    except sqlite3.OperationalError:
        return []
