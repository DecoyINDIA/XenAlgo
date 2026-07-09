from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LearningReport:
    generated_utc: str
    sleeves: dict[str, dict[str, Any]]
    regimes: list[dict[str, Any]]
    alpha_decay: list[dict[str, Any]]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_utc": self.generated_utc,
            "sleeves": self.sleeves,
            "regimes": self.regimes,
            "alpha_decay": self.alpha_decay,
            "summary": self.summary,
        }


class TradeJournalAnalytics:
    """Deterministic Phase 4 analytics derived only from persisted paper/live state."""

    def __init__(self, journal_path: str | Path) -> None:
        self.journal_path = str(journal_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.journal_path)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def build_report(self) -> LearningReport:
        with self._connect() as con:
            events = self._safe_fetch(
                con,
                """
                SELECT event_id, ts_utc, correlation_id, sleeve, symbol, side,
                       intended_qty, limit_price, state, filled_qty,
                       avg_fill_price, raw_json
                FROM order_events
                ORDER BY event_id ASC
                """,
            )
            portfolio = self._safe_fetch(
                con,
                """
                SELECT ts_utc, equity, cash, positions_value, day_pnl, peak_equity
                FROM portfolio_snapshots
                ORDER BY ts_utc ASC
                """,
            )

        sleeve_by_cid = self._sleeves_by_correlation(events)
        fills = self._deduped_fills(events, sleeve_by_cid)
        sleeves = self._sleeve_metrics(fills)
        regimes = self._regime_tags(portfolio)
        decay = self._alpha_decay(fills)
        summary = {
            "fill_count": len(fills),
            "sleeve_count": len(sleeves),
            "regime_count": len(regimes),
            "alpha_decay_checks": len(decay),
            "gross_notional": round(sum(item["gross_notional"] for item in sleeves.values()), 2),
        }
        return LearningReport(
            generated_utc=dt.datetime.now(dt.UTC).isoformat(),
            sleeves=sleeves,
            regimes=regimes,
            alpha_decay=decay,
            summary=summary,
        )

    def _sleeves_by_correlation(self, events: list[sqlite3.Row]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for event in events:
            sleeve = str(event["sleeve"] or "unknown")
            if sleeve != "unknown":
                mapping[str(event["correlation_id"])] = sleeve
        return mapping

    def _deduped_fills(
        self,
        events: list[sqlite3.Row],
        sleeve_by_cid: dict[str, str],
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        fills: list[dict[str, Any]] = []
        for event in events:
            if event["state"] != "TRADED" or not event["filled_qty"]:
                continue
            raw = _json(event["raw_json"])
            event_key = str(raw.get("event_key") or event["event_id"])
            if event_key in seen:
                continue
            seen.add(event_key)
            model_price = _float(raw.get("model_price"), event["limit_price"], event["avg_fill_price"], 0.0)
            fill_price = float(event["avg_fill_price"] or 0.0)
            qty = int(event["filled_qty"] or 0)
            side = str(event["side"] or "BUY").upper()
            slippage = fill_price - model_price if side == "BUY" else model_price - fill_price
            slippage_bps = (slippage / model_price * 10_000) if model_price else 0.0
            fills.append(
                {
                    "event_id": event["event_id"],
                    "ts_utc": event["ts_utc"],
                    "correlation_id": event["correlation_id"],
                    "sleeve": sleeve_by_cid.get(event["correlation_id"], event["sleeve"] or "unknown"),
                    "symbol": event["symbol"],
                    "side": side,
                    "qty": qty,
                    "model_price": model_price,
                    "fill_price": fill_price,
                    "gross_notional": abs(qty * fill_price),
                    "slippage": slippage,
                    "slippage_bps": slippage_bps,
                    "expected_return_pct": _optional_float(raw.get("expected_return_pct")),
                    "realized_return_pct": _optional_float(raw.get("realized_return_pct")),
                    "regime": raw.get("regime"),
                }
            )
        return fills

    def _sleeve_metrics(self, fills: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fill in fills:
            buckets[str(fill["sleeve"])].append(fill)

        metrics: dict[str, dict[str, Any]] = {}
        for sleeve, items in sorted(buckets.items()):
            buys = sum(item["qty"] for item in items if item["side"] == "BUY")
            sells = sum(item["qty"] for item in items if item["side"] == "SELL")
            gross = sum(item["gross_notional"] for item in items)
            slippage_inr = sum(item["slippage"] * item["qty"] for item in items)
            avg_slippage_bps = sum(item["slippage_bps"] for item in items) / len(items)
            realized = [
                item["realized_return_pct"]
                for item in items
                if item["realized_return_pct"] is not None
            ]
            expected = [
                item["expected_return_pct"]
                for item in items
                if item["expected_return_pct"] is not None
            ]
            metrics[sleeve] = {
                "fill_count": len(items),
                "symbols": sorted({str(item["symbol"]) for item in items}),
                "buy_qty": buys,
                "sell_qty": sells,
                "net_qty": buys - sells,
                "gross_notional": round(gross, 2),
                "slippage_inr": round(slippage_inr, 2),
                "avg_slippage_bps": round(avg_slippage_bps, 4),
                "expected_return_pct": round(sum(expected) / len(expected), 6) if expected else None,
                "realized_return_pct": round(sum(realized) / len(realized), 6) if realized else None,
            }
        return metrics

    def _regime_tags(self, portfolio: list[sqlite3.Row]) -> list[dict[str, Any]]:
        regimes: list[dict[str, Any]] = []
        for row in portfolio:
            equity = float(row["equity"] or 0.0)
            day_pnl = float(row["day_pnl"] or 0.0)
            peak = float(row["peak_equity"] or equity or 0.0)
            pnl_pct = day_pnl / equity if equity else 0.0
            drawdown_pct = (peak - equity) / peak if peak else 0.0
            if drawdown_pct >= 0.05:
                tag = "drawdown"
            elif pnl_pct >= 0.01:
                tag = "favorable"
            elif pnl_pct <= -0.01:
                tag = "adverse"
            else:
                tag = "normal"
            regimes.append(
                {
                    "ts_utc": row["ts_utc"],
                    "tag": tag,
                    "day_pnl_pct": round(pnl_pct, 6),
                    "drawdown_pct": round(drawdown_pct, 6),
                }
            )
        return regimes

    def _alpha_decay(self, fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        by_sleeve: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fill in fills:
            if fill["expected_return_pct"] is not None and fill["realized_return_pct"] is not None:
                by_sleeve[str(fill["sleeve"])].append(fill)
        for sleeve, items in sorted(by_sleeve.items()):
            expected = sum(float(item["expected_return_pct"]) for item in items) / len(items)
            realized = sum(float(item["realized_return_pct"]) for item in items) / len(items)
            gap = realized - expected
            status = "review" if gap < -0.01 else "ok"
            checks.append(
                {
                    "sleeve": sleeve,
                    "sample_size": len(items),
                    "expected_return_pct": round(expected, 6),
                    "realized_return_pct": round(realized, 6),
                    "edge_gap_pct": round(gap, 6),
                    "status": status,
                }
            )
        return checks

    def _safe_fetch(self, con: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
        try:
            return list(con.execute(sql).fetchall())
        except sqlite3.OperationalError:
            return []


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float(*values: Any) -> float:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return 0.0
