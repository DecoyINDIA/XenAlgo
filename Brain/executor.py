"""
Live executor — main orchestrator for paper and live swing trading.

Flow:
  1. Check market hours → skip if closed
  2. Get latest daily panel
  3. Run alphas → factor scores
  4. Generate target weights
  5. Compare current positions vs targets
  6. Generate and execute orders (SELL first, then BUY)
  7. Update position manager
  8. Log trades and portfolio snapshot
"""
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import pytz

from Brain.alpha_engine import AlphaEngine
from Brain.position_manager import LivePositionManager
from Brain.market_hours import (
    is_market_open,
    market_status,
    _now_ist,
)
from Brain.broker import PaperBroker
from Brain.portfolio_engine import PortfolioEngine

logger = logging.getLogger("QuantPlatform.LiveExecutor")

IST = pytz.timezone("Asia/Kolkata")


class LiveExecutor:
    """
    Orchestrates swing trading: daily data → signal → weights → trades.

    Two modes:
      - "paper": uses PaperBroker for simulated fills
      - "live":  intentionally disabled; sanctioned live orders must use xenalgo
    """

    def __init__(
        self,
        config: dict,
        mode: str = "paper",
        alpha_engine: Optional[AlphaEngine] = None,
        portfolio_engine: Optional[PortfolioEngine] = None,
        security_map: Optional[Dict[str, tuple]] = None,
        daily_panel: Optional[Dict[str, pd.DataFrame]] = None,
    ):
        self.config = config
        self.mode = mode
        if mode != "paper":
            raise RuntimeError("Brain live mode is quarantined; use xenalgo.execution only")
        self.security_map = security_map or {}
        self._daily_panel = daily_panel

        ltc = config.get("live_trading", {})
        self.results_dir = ltc.get("results_dir", "Diary/live")
        os.makedirs(self.results_dir, exist_ok=True)

        # Use main portfolio config (daily/swing)
        patched_config = dict(config)

        # Minimum holding bars (swing/delivery — can't sell same day)
        portfolio_cfg = config.get("portfolio", {})
        self.min_holding_bars = portfolio_cfg.get("min_holding_bars", 1)
        # Track when each position was first bought (bar index from panel)
        self._entry_bar: Dict[str, int] = {}

        # Core engines
        self.ae = alpha_engine or AlphaEngine("Strategies")
        self.pe = portfolio_engine or PortfolioEngine(patched_config)

        # Broker
        initial_cap = config["backtest"]["initial_capital"]
        self.broker = PaperBroker(initial_cap, patched_config)

        # Position manager (shared across modes)
        self.pos_mgr = LivePositionManager(config)

        # Trade/snapshot buffers for CSV logging
        self._trade_buffer: List[dict] = []
        self._snap_buffer: List[dict] = []

        logger.info(f"LiveExecutor initialized (mode={mode})")

    # ── main public API ─────────────────────────────────────────────────

    def run_once(self) -> Optional[Dict[str, int]]:
        """
        Execute one trading iteration using the daily panel.
        Returns dict with trade counts or None if skipped.
        """
        if not is_market_open():
            logger.info(f"Market closed. {market_status()}")
            return None

        panel = self._daily_panel
        if panel is None or panel.get("close", pd.DataFrame()).empty:
            logger.warning("No daily panel data available — skipping iteration.")
            return None

        # 2. Discover and run alphas (skip if already loaded)
        alphas = list(self.ae.alphas.keys()) or self.ae.discover_alphas()
        if not alphas:
            logger.warning("No alphas discovered — skipping.")
            return None

        all_trades = []
        for name in alphas:
            try:
                factor_scores = self.ae.run_alpha(name, panel)
                if factor_scores is None or factor_scores.empty:
                    continue

                target_weights = self.pe.generate_target_weights(factor_scores, panel)

                current_positions = self._get_current_positions()
                orders = self._generate_orders(
                    name, target_weights, panel, current_positions
                )

                for order in orders:
                    result = self._execute_order(order)
                    if result:
                        all_trades.append(result)
                        self._log_trade(result)

            except Exception as e:
                logger.error(f"Alpha {name} failed: {e}")

        # Log snapshot
        self._log_snapshot()

        result = {"trades": len(all_trades), "alphas": len(alphas)}
        logger.info(f"Iteration complete: {result}")
        return result

    def square_off(self) -> List[dict]:
        """Close all open positions immediately."""
        logger.info("SQUARE OFF initiated")
        return self._square_off_internal()

    def status(self) -> dict:
        """Return current trading status summary."""
        positions = self._get_current_positions()
        pos_df = self.pos_mgr.to_dataframe()
        pnl = {}

        # For paper mode, get portfolio value
        port_val = None
        cash = None
        if hasattr(self.broker, "get_portfolio_value"):
            port_val = self.broker.get_portfolio_value()
            cash = self.broker.get_funds().get("cash", 0)

        return {
            "mode": self.mode,
            "market": market_status(),
            "positions": positions,
            "position_count": len(positions),
            "portfolio_value": port_val,
            "cash": cash,
            "positions_df": pos_df,
        }

    # ── private: order generation ───────────────────────────────────────

    def _generate_orders(
        self,
        alpha_name: str,
        target_weights: pd.DataFrame,
        panel: Dict[str, pd.DataFrame],
        current_positions: Dict[str, int],
    ) -> List[dict]:
        """
        Compare target weights with current positions and generate orders.
        Follows backtest convention: SELL first, then BUY.
        """
        if target_weights.empty:
            return []

        # Get the latest bar's target weights
        latest_idx = target_weights.index[-1]
        targets = target_weights.loc[latest_idx]
        close_prices = panel["close"].loc[panel["close"].index[-1]]

        # Convert target weights to target shares
        port_val = self._get_portfolio_value()
        if port_val <= 0:
            return []

        target_shares = {}
        for sym in targets.index:
            w = targets[sym]
            px = close_prices.get(sym, 0)
            if pd.isna(px) or px <= 0:
                continue
            target_shares[sym] = int((w * port_val) / px)

        current_shares = {
            sym: current_positions.get(sym, 0) for sym in targets.index
        }

        # Determine deltas
        deltas = {}
        for sym in targets.index:
            diff = target_shares.get(sym, 0) - current_shares.get(sym, 0)
            if diff != 0:
                deltas[sym] = diff

        # Current bar index for holding period check
        current_bar = len(panel["close"]) - 1

        # Generate orders: SELL (negative delta) first, then BUY (positive delta)
        orders = []
        for sym, delta in sorted(deltas.items(), key=lambda x: (x[1] > 0, abs(x[1]))):
            if delta < 0:
                # Minimum holding period — skip sell if bought too recently
                if self.min_holding_bars > 0:
                    entry = self._entry_bar.get(sym)
                    held = current_bar - entry if entry is not None else 0
                    if held < self.min_holding_bars:
                        logger.info(
                            f"SKIP SELL {sym}: held {held} bar(s), "
                            f"need {self.min_holding_bars} (min_holding_bars)"
                        )
                        continue
                orders.append({
                    "symbol": sym,
                    "action": "SELL",
                    "quantity": abs(delta),
                    "price": close_prices.get(sym, 0),
                    "alpha": alpha_name,
                })
        for sym, delta in sorted(deltas.items(), key=lambda x: (x[1] > 0, abs(x[1]))):
            if delta > 0:
                orders.append({
                    "symbol": sym,
                    "action": "BUY",
                    "quantity": delta,
                    "price": close_prices.get(sym, 0),
                    "alpha": alpha_name,
                })

        return orders

    def _execute_order(self, order: dict) -> Optional[dict]:
        """Execute a single order through the broker, respecting risk limits."""
        sym = order["symbol"]
        qty = order["quantity"]
        action = order["action"]
        price = order["price"]

        if qty <= 0 or price <= 0:
            return None

        # Risk check
        port_val = self._get_portfolio_value()
        allowed, reason = self.pos_mgr.check_order_limits(sym, qty, price, port_val)
        if not allowed:
            logger.warning(f"Risk limit blocked: {action} {qty} {sym} — {reason}")
            return None

        # If scaled down, use adjusted quantity
        if "Scale down" in reason:
            scaled = int(reason.split("to ")[1].split(" ")[0]) if "to " in reason else qty
            if self.mode == "live":
                qty = scaled

        # Execute
        result = self.broker.place_order(
            symbol=sym,
            action=action,
            quantity=qty,
            price=price,
        )

        if result.get("status") in ("TRADED", "PENDING", "ACCEPTED"):
            filled_qty = result.get("quantity", qty)
            filled_price = result.get("price", price)
            self.pos_mgr.update_position(
                sym,
                filled_qty if action == "BUY" else -filled_qty,
                filled_price,
            )
            # Track entry bar for minimum holding period check
            if action == "BUY" and self._daily_panel:
                current_bar = len(self._daily_panel["close"]) - 1
                # Only record if this is a new position (not adding to existing)
                prev_qty = sum(1 for s in self.pos_mgr._positions if s == sym)
                if sym not in self._entry_bar:
                    self._entry_bar[sym] = current_bar
            elif action == "SELL":
                # Clear entry tracking if fully sold
                remaining = self.pos_mgr._positions.get(sym, {}).get("qty", 0)
                if remaining <= 0:
                    self._entry_bar.pop(sym, None)
            return {
                "timestamp": _now_ist().isoformat(),
                "symbol": sym,
                "action": action,
                "quantity": filled_qty,
                "price": filled_price,
                "status": result.get("status"),
                "alpha": order.get("alpha"),
            }

        logger.warning(f"Order failed: {action} {qty} {sym} — {result}")
        return None

    # ── private: square-off ─────────────────────────────────────────────

    def _square_off_internal(self) -> List[dict]:
        """Close all positions. Returns list of sell orders."""
        symbols = self.pos_mgr.symbols_to_square()
        if not symbols:
            logger.info("No positions to square off.")
            return []

        # Use daily panel close prices
        prices = {}
        if self._daily_panel:
            last_close = self._daily_panel["close"].iloc[-1] if not self._daily_panel["close"].empty else None
            if last_close is not None:
                prices = last_close.to_dict()

        orders = []
        for sym in symbols:
            px = prices.get(sym, 0)
            if px <= 0:
                continue
            qty = self.pos_mgr._positions.get(sym, {}).get("qty", 0)
            if qty <= 0:
                continue
            result = self.broker.place_order(sym, "SELL", qty, px)
            if result.get("status") in ("TRADED", "PENDING", "ACCEPTED"):
                self.pos_mgr.update_position(sym, -qty, px)
                orders.append({
                    "timestamp": _now_ist().isoformat(),
                    "symbol": sym,
                    "action": "SELL",
                    "quantity": qty,
                    "status": "SQUARED_OFF",
                })
                logger.info(f"Square off: SELL {qty} {sym} @ {px:.2f}")

        self._flush_logs()
        return orders

    # ── private: helpers ────────────────────────────────────────────────

    def _get_current_positions(self) -> Dict[str, int]:
        """Get current positions from broker, reconciled with position manager."""
        if self.mode == "paper":
            raw = self.broker.get_positions()
            return {sym: pos.get("quantity", 0) for sym, pos in raw.items()}
        else:
            raw_list = self.broker.get_positions()
            # dhanhq returns list of dicts with 'tradingSymbol' and 'buyQty' etc.
            raw = {}
            for p in raw_list:
                sym = p.get("tradingSymbol", "")
                qty = int(p.get("netQty", p.get("buyQty", 0)))
                if sym:
                    raw[sym] = qty
                    self.pos_mgr.update_position(sym, qty, float(p.get("avgPrice", 0)))

        return dict(raw)

    def _get_portfolio_value(self) -> float:
        """Get current portfolio value from broker."""
        if self.mode == "paper":
            return self.broker.get_portfolio_value()
        try:
            funds = self.broker.get_fund_limits()
            data = funds.get("data", funds)
            return float(data.get("totalBalance", data.get("balance", 0)))
        except Exception:
            return self.config["backtest"]["initial_capital"]

    # ── private: logging ────────────────────────────────────────────────

    def _log_trade(self, trade: dict) -> None:
        self._trade_buffer.append(trade)

    def _log_snapshot(self) -> None:
        positions = self._get_current_positions()
        port_val = self._get_portfolio_value()
        self._snap_buffer.append({
            "timestamp": _now_ist().isoformat(),
            "portfolio_value": round(port_val, 2),
            "position_count": len(positions),
            "mode": self.mode,
        })

    def _flush_logs(self) -> None:
        """Write buffered trades and snapshots to CSV files, then clear."""
        if self._trade_buffer:
            path = os.path.join(self.results_dir, "trade_log.csv")
            new_df = pd.DataFrame(self._trade_buffer)
            # Append to existing file if it exists
            if os.path.exists(path):
                existing = pd.read_csv(path)
                combined = pd.concat([existing, new_df], ignore_index=True)
                combined.to_csv(path, index=False)
            else:
                new_df.to_csv(path, index=False)
            logger.info(f"Flushed {len(self._trade_buffer)} trades to {path}")
            self._trade_buffer.clear()

        if self._snap_buffer:
            path = os.path.join(self.results_dir, "portfolio_snapshots.csv")
            new_df = pd.DataFrame(self._snap_buffer)
            if os.path.exists(path):
                existing = pd.read_csv(path)
                combined = pd.concat([existing, new_df], ignore_index=True)
                combined.to_csv(path, index=False)
            else:
                new_df.to_csv(path, index=False)
            self._snap_buffer.clear()
