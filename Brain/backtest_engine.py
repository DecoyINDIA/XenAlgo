import logging
import math
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger("QuantPlatform.BacktestEngine")

class BacktestEngine:
    """
    Executes a daily backtest simulation using target weights and a price panel.
    Accounts for realistic costs, slippage, cash constraints, and benchmarks.
    """
    def __init__(self, config: dict):
        self.config = config
        self.backtest_cfg = config["backtest"]
        self.costs_cfg = config["costs"]
        self.portfolio_cfg = config.get("portfolio", {})
        self.initial_capital = self.backtest_cfg.get("initial_capital", 10000000.0)

    def run(
        self, 
        target_weights: pd.DataFrame, 
        panel: Dict[str, pd.DataFrame],
        benchmark_series: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        Runs the daily simulation and returns full portfolio metrics, trade logs,
        and daily returns.
        """
        open_df = panel["open"]
        high_df = panel["high"]
        low_df = panel["low"]
        close_df = panel["close"]
        volume_df = panel["volume"]
        
        dates = close_df.index
        symbols = close_df.columns
        
        # Check that target_weights align with the panel
        target_weights = target_weights.reindex(index=dates, columns=symbols).fillna(0.0)
        
        # Initialize portfolio state
        cash = self.initial_capital
        positions = {sym: 0 for sym in symbols} # holding shares
        last_buy_bar: Dict[str, int] = {}  # bar index when each position was last bought
        
        portfolio_history = []
        trade_log = []
        
        logger.info(f"Starting backtest simulation from {dates[0].date()} to {dates[-1].date()}...")
        
        # Loop day-by-day
        for i, date in enumerate(dates):
            open_prices = open_df.iloc[i]
            close_prices = close_df.iloc[i]
            
            # 1. Valuation at market open (using yesterday's positions and today's open price)
            open_holdings_value = sum(positions[sym] * open_prices[sym] for sym in symbols if positions[sym] != 0)
            portfolio_open_val = cash + open_holdings_value
            
            # Get current day's target weights
            target_weights_t = target_weights.iloc[i]
            
            # Check if we need to rebalance today (target weights changed or differs from current weights)
            # Calculate current weights at open
            current_weights = pd.Series(0.0, index=symbols)
            for sym in symbols:
                if positions[sym] != 0 and portfolio_open_val > 0:
                    current_weights[sym] = (positions[sym] * open_prices[sym]) / portfolio_open_val
            
            # If target weights are different, let's rebalance
            weights_diff = target_weights_t - current_weights
            
            if not weights_diff.eq(0).all():
                # Rebalance execution:
                # SELLS first, then BUYS — prevents cash shortfall
                sell_symbols = weights_diff[weights_diff < 0].index
                buy_symbols = weights_diff[weights_diff > 0].index
                
                # Execute Sells
                rebal_pct = self.portfolio_cfg.get("rebalance_threshold_pct", 0.0)
                min_hold = self.portfolio_cfg.get("min_holding_bars", 0)
                min_val = self.portfolio_cfg.get("min_trade_value", 0)

                for sym in sell_symbols:
                    target_w = target_weights_t[sym]
                    current_w = current_weights[sym]

                    # Drift threshold — skip if weight deviation is within dead band
                    if rebal_pct > 0:
                        max_dev = abs(target_w) * rebal_pct / 100.0
                        if abs(current_w - target_w) <= max_dev:
                            continue

                    # Minimum holding period — don't sell recently bought positions
                    if min_hold > 0 and positions.get(sym, 0) > 0:
                        held = i - last_buy_bar.get(sym, -999)
                        if held < min_hold:
                            continue

                    target_val = target_w * portfolio_open_val
                    current_val = positions[sym] * open_prices[sym]

                    diff_val = target_val - current_val
                    if diff_val < 0: # Double check it is a sell
                        sell_val_target = abs(diff_val)
                        open_price = open_prices[sym]

                        if pd.isna(open_price) or open_price <= 0:
                            continue

                        # Apply sell slippage
                        execution_price = open_price * (1.0 - self.costs_cfg.get("slippage_pct", 0.0005))

                        # Number of shares to sell
                        shares_to_sell = int(sell_val_target / execution_price)
                        # LongOnly: never sell more than we own
                        if shares_to_sell > positions[sym]:
                            shares_to_sell = max(0, positions[sym])

                        if shares_to_sell > 0:
                            trade_val = shares_to_sell * execution_price

                            # Minimum trade value — skip tiny trades
                            if min_val > 0 and trade_val < min_val:
                                continue

                            costs = self._calculate_transaction_costs(trade_val, is_buy=False)

                            positions[sym] -= shares_to_sell
                            cash += (trade_val - costs)

                            trade_log.append({
                                "date": date,
                                "symbol": sym,
                                "action": "SELL",
                                "shares": shares_to_sell,
                                "price": execution_price,
                                "value": trade_val,
                                "costs": costs,
                                "net_cash_flow": trade_val - costs
                            })

                # Execute Buys
                for sym in buy_symbols:
                    target_w = target_weights_t[sym]
                    current_w = current_weights[sym]

                    # Drift threshold — skip if weight deviation is within dead band
                    if rebal_pct > 0:
                        max_dev = abs(target_w) * rebal_pct / 100.0
                        if abs(current_w - target_w) <= max_dev:
                            continue

                    target_val = target_w * portfolio_open_val
                    current_val = positions[sym] * open_prices[sym]

                    diff_val = target_val - current_val
                    if diff_val > 0: # Double check it is a buy
                        buy_val_target = diff_val
                        open_price = open_prices[sym]

                        if pd.isna(open_price) or open_price <= 0:
                            continue

                        # Apply buy slippage
                        execution_price = open_price * (1.0 + self.costs_cfg.get("slippage_pct", 0.0005))

                        # Calculate maximum shares we can afford with cash management
                        shares_to_buy = int(buy_val_target / execution_price)

                        if shares_to_buy > 0:
                            trade_val = shares_to_buy * execution_price

                            # Minimum trade value — skip tiny trades
                            if min_val > 0 and trade_val < min_val:
                                continue

                            costs = self._calculate_transaction_costs(trade_val, is_buy=True)
                            total_needed = trade_val + costs

                            # Scaling down if cash is insufficient
                            if total_needed > cash:
                                approx_cost_pct = (self.costs_cfg["brokerage_pct"] +
                                                   self.costs_cfg["exchange_charges_pct"] +
                                                   self.costs_cfg["stamp_duty_pct"] +
                                                   self.costs_cfg["sebi_charges_pct"])
                                scaled_shares = int(cash / (execution_price * (1.0 + approx_cost_pct)))
                                shares_to_buy = max(0, scaled_shares)
                                trade_val = shares_to_buy * execution_price

                                if min_val > 0 and trade_val < min_val:
                                    continue

                                costs = self._calculate_transaction_costs(trade_val, is_buy=True)
                                total_needed = trade_val + costs

                            if shares_to_buy > 0 and cash >= total_needed:
                                positions[sym] += shares_to_buy
                                cash -= total_needed
                                last_buy_bar[sym] = i  # track for min holding check

                                trade_log.append({
                                    "date": date,
                                    "symbol": sym,
                                    "action": "BUY",
                                    "shares": shares_to_buy,
                                    "price": execution_price,
                                    "value": trade_val,
                                    "costs": costs,
                                    "net_cash_flow": -total_needed
                                })
            
            # 2. Valuation at market close (using updated positions and today's close price)
            close_holdings_value = 0.0
            for sym in symbols:
                pos = positions[sym]
                if pos != 0:
                    c_price = close_prices[sym]
                    if pd.isna(c_price) or c_price <= 0:
                        # Fallback to open price if close is missing
                        c_price = open_prices[sym] if (not pd.isna(open_prices[sym]) and open_prices[sym] > 0) else 0.0
                    close_holdings_value += pos * c_price
                    
            portfolio_close_val = cash + close_holdings_value
            
            # Record portfolio history
            portfolio_history.append({
                "date": date,
                "cash": cash,
                "holdings_value": close_holdings_value,
                "portfolio_value": portfolio_close_val,
            })
            
        # Convert history to DataFrame
        history_df = pd.DataFrame(portfolio_history)
        history_df.set_index("date", inplace=True)
        
        # Calculate daily returns
        history_df["returns"] = history_df["portfolio_value"].pct_change().fillna(0.0)
        history_df["equity_curve"] = history_df["portfolio_value"] / self.initial_capital
        
        # Calculate benchmark returns
        if benchmark_series is not None:
            # Reindex benchmark to match our dates
            benchmark_series = benchmark_series.reindex(dates).ffill().bfill()
            benchmark_returns = benchmark_series.pct_change().fillna(0.0)
            history_df["benchmark_returns"] = benchmark_returns
            history_df["benchmark_curve"] = (1.0 + benchmark_returns).cumprod()
        else:
            # Fallback benchmark: Equal-weighted return of all stocks in the universe
            daily_stock_returns = close_df.pct_change(fill_method=None).fillna(0.0)
            mean_returns = daily_stock_returns.mean(axis=1)
            history_df["benchmark_returns"] = mean_returns
            history_df["benchmark_curve"] = (1.0 + mean_returns).cumprod()
            
        trade_log_df = pd.DataFrame(trade_log)
        
        logger.info(f"Backtest complete. Final portfolio value: INR {portfolio_close_val:,.2f}")
        return {
            "history": history_df,
            "trades": trade_log_df,
            "positions": positions
        }

    def _calculate_transaction_costs(self, trade_value: float, is_buy: bool) -> float:
        """
        Calculates NSE transaction taxes and fees on Indian stock markets:
        Brokerage, STT, GST, Exchange charges, Stamp Duty, and SEBI charges.
        """
        if trade_value <= 0:
            return 0.0
            
        brokerage = self.costs_cfg.get("brokerage_pct", 0.0005) * trade_value
        exchange_charges = self.costs_cfg.get("exchange_charges_pct", 0.0000345) * trade_value
        
        gst = self.costs_cfg.get("gst_pct", 0.18) * (brokerage + exchange_charges)
        sebi_charges = self.costs_cfg.get("sebi_charges_pct", 0.000001) * trade_value
        
        stt = 0.0
        stamp_duty = 0.0
        
        if is_buy:
            stt = self.costs_cfg.get("stt_buy_pct", 0.0010) * trade_value
            stamp_duty = self.costs_cfg.get("stamp_duty_pct", 0.00015) * trade_value
        else:
            stt = self.costs_cfg.get("stt_sell_pct", 0.0010) * trade_value
            
        total_costs = brokerage + exchange_charges + gst + sebi_charges + stt + stamp_duty
        return total_costs
