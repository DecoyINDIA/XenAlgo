"""
Risk-aware position tracker. Used by both paper and live trading modes.

Enforces:
- Max 10 % of portfolio per position
- Max total positions
"""
import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("QuantPlatform.PositionManager")


class LivePositionManager:
    """
    Tracks open positions, enforces risk limits, and computes P&L.
    """

    def __init__(self, config: dict):
        ltc = config.get("live_trading", {})
        self.max_position_pct = ltc.get("max_position_pct", 0.10)  # 10%
        self.max_positions = ltc.get("max_positions", 10)
        # positions: {symbol: {"qty": int, "avg_price": float}}
        self._positions: Dict[str, dict] = {}

    # ── position tracking ───────────────────────────────────────────────

    def update_position(self, symbol: str, qty: int, price: float) -> None:
        """
        Update tracked position after an order fills.

        BUY: qty > 0  — adds to position, recalculates avg price
        SELL: qty < 0 — reduces position; removes entry if qty reaches 0
        """
        current = self._positions.get(symbol)
        if current is None:
            if qty > 0:
                self._positions[symbol] = {"qty": qty, "avg_price": price}
            return

        if qty > 0:  # buy
            total_qty = current["qty"] + qty
            total_cost = current["qty"] * current["avg_price"] + qty * price
            current["qty"] = total_qty
            current["avg_price"] = total_cost / total_qty if total_qty else 0
        else:  # sell
            current["qty"] += qty  # qty is negative for sell
            if current["qty"] <= 0:
                del self._positions[symbol]

    def set_positions(self, positions: Dict[str, dict]) -> None:
        """Bulk-replace positions (e.g. from broker reconciliation)."""
        self._positions = dict(positions)

    def get_open_positions(self) -> Dict[str, dict]:
        return dict(self._positions)

    @property
    def position_count(self) -> int:
        return len(self._positions)

    # ── risk checks ─────────────────────────────────────────────────────

    def check_order_limits(
        self, symbol: str, qty: int, price: float, portfolio_value: float
    ) -> Tuple[bool, str]:
        """
        Check if an order passes risk limits.

        Returns (allowed: bool, reason: str).
        """
        if portfolio_value <= 0 or price <= 0:
            return False, "Invalid portfolio value or price"

        # Max positions check (only for NEW positions)
        if symbol not in self._positions and len(self._positions) >= self.max_positions:
            return False, f"Max positions ({self.max_positions}) reached"

        # Max position size: existing + new should not exceed max_position_pct
        existing_val = self._positions.get(symbol, {}).get("qty", 0) * price
        new_val = qty * price
        total_val = existing_val + (new_val if symbol not in self._positions else new_val)
        exposure_pct = total_val / portfolio_value

        if exposure_pct > self.max_position_pct:
            max_qty = int((self.max_position_pct * portfolio_value) / price)
            current_qty = self._positions.get(symbol, {}).get("qty", 0)
            allowed_new = max_qty - (current_qty if symbol in self._positions else 0)
            if allowed_new <= 0:
                return (
                    False,
                    f"Position would exceed {self.max_position_pct*100:.0f}% limit "
                    f"(exposure: {exposure_pct*100:.1f}%)",
                )
            # Allow scaled-down
            return True, f"Scale down to {allowed_new} shares (limit: {self.max_position_pct*100:.0f}%)"

        return True, "OK"

    def get_exposure_pct(self, prices: Dict[str, float]) -> float:
        """Total position exposure as % of portfolio (mark-to-market)."""
        total = sum(
            pos["qty"] * prices.get(sym, pos["avg_price"])
            for sym, pos in self._positions.items()
        )
        return total / max(total, 1)

    # ── P&L ─────────────────────────────────────────────────────────────

    def compute_pnl(self, prices: Dict[str, float]) -> Dict[str, float]:
        """Compute unrealised P&L per symbol and total."""
        total = 0.0
        details = {}
        for sym, pos in self._positions.items():
            px = prices.get(sym, pos["avg_price"])
            pnl = pos["qty"] * (px - pos["avg_price"])
            details[sym] = round(pnl, 2)
            total += pnl
        return {"total": round(total, 2), "details": details}

    # ── square-off ──────────────────────────────────────────────────────

    def symbols_to_square(self) -> List[str]:
        """Return list of symbols with open positions that need squaring off."""
        return list(self._positions.keys())

    def to_dataframe(self) -> pd.DataFrame:
        """Return positions as a DataFrame for display/logging."""
        rows = []
        for sym, pos in self._positions.items():
            rows.append({"symbol": sym, "qty": pos["qty"], "avg_price": pos["avg_price"]})
        return pd.DataFrame(rows) if rows else pd.DataFrame()
