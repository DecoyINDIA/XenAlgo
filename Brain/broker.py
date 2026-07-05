"""
Paper broker — simulated order execution with realistic costs.
Same cost model as BacktestEngine._calculate_transaction_costs.

Interface mirrors what LiveOrderManager will expose so LiveExecutor
can swap between the two by changing one reference.
"""
import logging
import pandas as pd
from typing import Dict, List, Optional

logger = logging.getLogger("QuantPlatform.PaperBroker")


class PaperBroker:
    """
    Simulated broker for paper trading. Tracks cash, positions, and fills
    orders at simulated market prices with slippage + transaction costs.
    """

    def __init__(self, initial_capital: float, config: dict):
        self.costs_cfg = config.get("costs", {})
        self.initial_capital = initial_capital
        self.cash = initial_capital
        # positions: {symbol: {"quantity": int, "avg_price": float}}
        self._positions: Dict[str, dict] = {}
        self._trade_log: List[dict] = []

    # ── public API (matches LiveOrderManager interface) ──────────────────

    def place_order(
        self,
        symbol: str,
        action: str,  # "BUY" or "SELL"
        quantity: int,
        price: float,
        order_type: str = "MARKET",
    ) -> dict:
        """
        Simulate an order fill at the given price with slippage + costs.
        Returns a dict matching dhanhq's order response shape.
        """
        if quantity <= 0 or price <= 0:
            return {"status": "REJECTED", "reason": "Invalid quantity or price"}

        slippage = self.costs_cfg.get("slippage_pct", 0.0005)
        exec_price = price * (1 + slippage) if action == "BUY" else price * (1 - slippage)
        trade_value = quantity * exec_price
        costs = self._calculate_costs(trade_value, is_buy=(action == "BUY"))

        if action == "BUY":
            total_needed = trade_value + costs
            if total_needed > self.cash:
                # scale down to available cash
                max_shares = int(self.cash / (exec_price * 1.002))  # ~0.2% buffer
                if max_shares <= 0:
                    return {"status": "REJECTED", "reason": "Insufficient cash"}
                quantity = max_shares
                trade_value = quantity * exec_price
                costs = self._calculate_costs(trade_value, is_buy=True)
                total_needed = trade_value + costs

            self.cash -= total_needed
            if symbol in self._positions:
                old = self._positions[symbol]
                total_qty = old["quantity"] + quantity
                total_cost = old["quantity"] * old["avg_price"] + trade_value
                self._positions[symbol] = {
                    "quantity": total_qty,
                    "avg_price": total_cost / total_qty if total_qty else 0,
                }
            else:
                self._positions[symbol] = {"quantity": quantity, "avg_price": exec_price}
        else:  # SELL
            held = self._positions.get(symbol, {}).get("quantity", 0)
            sell_qty = min(quantity, held)
            if sell_qty <= 0:
                return {"status": "REJECTED", "reason": "No position to sell"}
            # Recompute with actual sold qty
            quantity = sell_qty
            trade_value = quantity * exec_price
            costs = self._calculate_costs(trade_value, is_buy=False)
            self.cash += trade_value - costs
            self._positions[symbol]["quantity"] -= quantity
            if self._positions[symbol]["quantity"] <= 0:
                del self._positions[symbol]

        self._trade_log.append({
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": round(exec_price, 2),
            "value": round(trade_value, 2),
            "costs": round(costs, 2),
            "net_cash_flow": round(-total_needed if action == "BUY" else trade_value - costs, 2),
        })

        logger.info(
            f"[PAPER] {action} {quantity} {symbol} @ {exec_price:.2f} "
            f"(costs: {costs:.2f}, cash: {self.cash:.2f})"
        )
        return {
            "status": "TRADED",
            "order_id": f"paper_{len(self._trade_log)}",
            "quantity": quantity,
            "price": round(exec_price, 2),
        }

    def get_positions(self) -> Dict[str, dict]:
        """Returns {symbol: {"quantity": int, "avg_price": float}}."""
        return dict(self._positions)

    def get_portfolio_value(self, prices: Optional[Dict[str, float]] = None) -> float:
        """
        Portfolio value = cash + mark-to-market of positions.
        If prices is None, uses avg_price as proxy.
        """
        holdings = 0.0
        for sym, pos in self._positions.items():
            px = prices.get(sym, pos["avg_price"]) if prices else pos["avg_price"]
            holdings += pos["quantity"] * px
        return self.cash + holdings

    def get_funds(self) -> dict:
        """Returns cash and portfolio value summary."""
        return {
            "cash": round(self.cash, 2),
            "initial_capital": self.initial_capital,
            "positions_value": round(self.get_portfolio_value() - self.cash, 2),
        }

    def square_off(self, prices: Optional[Dict[str, float]] = None) -> List[dict]:
        """Close all open positions. Returns list of sell orders placed."""
        orders = []
        for sym in list(self._positions.keys()):
            pos = self._positions[sym]
            if pos["quantity"] > 0:
                px = prices.get(sym, pos["avg_price"]) if prices else pos["avg_price"]
                result = self.place_order(sym, "SELL", pos["quantity"], px)
                orders.append(result)
        return orders

    @property
    def trade_log(self) -> pd.DataFrame:
        return pd.DataFrame(self._trade_log)

    # ── private helpers ─────────────────────────────────────────────────

    def _calculate_costs(self, trade_value: float, is_buy: bool) -> float:
        """Same cost formula as BacktestEngine._calculate_transaction_costs."""
        if trade_value <= 0:
            return 0.0
        brokerage = self.costs_cfg.get("brokerage_pct", 0.0005) * trade_value
        exchange_charges = self.costs_cfg.get("exchange_charges_pct", 0.0000345) * trade_value
        gst = self.costs_cfg.get("gst_pct", 0.18) * (brokerage + exchange_charges)
        sebi_charges = self.costs_cfg.get("sebi_charges_pct", 0.000001) * trade_value
        stt = (self.costs_cfg.get("stt_buy_pct" if is_buy else "stt_sell_pct", 0.0010)) * trade_value
        stamp_duty = self.costs_cfg.get("stamp_duty_pct", 0.00015) * trade_value if is_buy else 0.0
        return brokerage + exchange_charges + gst + sebi_charges + stt + stamp_duty
