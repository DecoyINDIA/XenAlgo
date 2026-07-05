import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional

logger = logging.getLogger("QuantPlatform.PortfolioEngine")

class PortfolioEngine:
    """
    Converts alpha factor scores into target weights based on configured rules:
    LongOnly vs LongShort, rebalancing schedules, position sizing, and liquidity filters.
    """
    def __init__(self, config: dict):
        self.config = config
        self.portfolio_cfg = config["portfolio"]
        self.costs_cfg = config["costs"]
        self.universe_cfg = config["universe"]

    def generate_target_weights(
        self, factor_scores: pd.DataFrame, panel: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        Processes factor scores to produce a daily DataFrame of target portfolio weights.
        Ensures NO LOOKAHEAD BIAS by lagging the signals by 1 day.
        """
        close_df = panel["close"]
        volume_df = panel["volume"]
        
        dates = close_df.index
        symbols = close_df.columns
        
        # 1. Align factor scores to the exact close index/columns
        # Reindex factor scores to match the price panel
        aligned_factors = factor_scores.reindex(index=dates, columns=symbols)
        
        # Lag factors by 1 day to ensure signals at t-1 are used for trading on day t
        lagged_factors = aligned_factors.shift(1)
        
        # Initialize target weights DataFrame with zeros
        target_weights = pd.DataFrame(0.0, index=dates, columns=symbols)
        
        # 2. Identify rebalancing days
        rebalance_days = self._get_rebalance_days(dates)
        
        # 3. Calculate Liquidity Filter components
        # Calculate rolling average volume
        liq_days = self.portfolio_cfg.get("min_liquidity_days", 20)
        roll_vol = volume_df.rolling(window=liq_days).mean()
        roll_close = close_df.rolling(window=1).mean() # just daily close
        
        # Loop through dates to assign weights
        last_weights = pd.Series(0.0, index=symbols)
        
        for i, date in enumerate(dates):
            # If not a rebalance day, keep the previous day's target weights
            if not rebalance_days[i]:
                target_weights.iloc[i] = last_weights
                continue
                
            # It's a rebalance day! Compute new weights based on t-1 data (lagged factors)
            factor_row = lagged_factors.iloc[i]
            
            # If no signal is available yet (warmup period), assign zero weights
            if factor_row.isna().all():
                target_weights.iloc[i] = 0.0
                last_weights = target_weights.iloc[i]
                continue
                
            # Apply liquidity filters on t-1 data
            vol_row = roll_vol.iloc[i-1] if i > 0 else roll_vol.iloc[i]
            price_row = roll_close.iloc[i-1] if i > 0 else roll_close.iloc[i]
            
            min_price = self.universe_cfg.get("min_price", 10.0)
            min_vol = self.universe_cfg.get("min_volume", 10000.0)
            
            # Filter symbols that meet liquidity requirements
            eligible_mask = (vol_row >= min_vol) & (price_row >= min_price) & (~factor_row.isna())
            eligible_symbols = symbols[eligible_mask]
            
            if len(eligible_symbols) == 0:
                target_weights.iloc[i] = 0.0
                last_weights = target_weights.iloc[i]
                continue
                
            # Extract factor scores for eligible symbols
            scores = factor_row[eligible_symbols]
            
            # Compute weights based on long/short configuration
            weights_row = pd.Series(0.0, index=symbols)
            
            portfolio_type = self.portfolio_cfg.get("type", "LongOnly")
            max_pos = self.portfolio_cfg.get("max_positions", 20)
            sizing_method = self.portfolio_cfg.get("sizing", "EqualWeight")
            
            if portfolio_type == "LongOnly":
                # Select top N factors
                top_symbols = scores.nlargest(max_pos)
                if not top_symbols.empty:
                    weights_row[top_symbols.index] = self._compute_weights(
                        top_symbols, sizing_method, price_row, vol_row, is_long=True
                    )
            else:
                logger.warning(f"Unsupported portfolio type '{portfolio_type}'. Defaulting to LongOnly.")
                top_symbols = scores.nlargest(max_pos)
                if not top_symbols.empty:
                    weights_row[top_symbols.index] = self._compute_weights(
                        top_symbols, sizing_method, price_row, vol_row, is_long=True
                    )
            
            target_weights.iloc[i] = weights_row
            last_weights = weights_row
            
        return target_weights

    def _get_rebalance_days(self, dates: pd.DatetimeIndex) -> List[bool]:
        """
        Creates a boolean mask indicating rebalancing days based on rebalance_freq.
        """
        freq = self.portfolio_cfg.get("rebalance_freq", "Weekly")
        rebalance_day = self.portfolio_cfg.get("rebalance_day", 0) # Monday by default
        
        rebalance_days = [False] * len(dates)
        if len(dates) == 0:
            return rebalance_days
            
        # First trading day is always a rebalance day to initialize portfolio
        rebalance_days[0] = True
        
        if freq == "Daily":
            return [True] * len(dates)
            
        elif freq == "Weekly":
            # Rebalance when the calendar week changes or on a specific weekday
            for i in range(1, len(dates)):
                prev_date = dates[i-1]
                curr_date = dates[i]
                
                # Option 1: Week number changes
                if curr_date.isocalendar()[1] != prev_date.isocalendar()[1]:
                    rebalance_days[i] = True
                # Option 2: It is the target rebalance day and we haven't rebalanced this week
                elif curr_date.weekday() == rebalance_day and prev_date.weekday() != rebalance_day:
                    rebalance_days[i] = True
                    
        elif freq == "Monthly":
            # Rebalance when the month changes
            for i in range(1, len(dates)):
                if dates[i].month != dates[i-1].month:
                    rebalance_days[i] = True
                    
        return rebalance_days

    def _compute_weights(
        self, 
        selected_scores: pd.Series, 
        sizing_method: str, 
        price_row: pd.Series, 
        vol_row: pd.Series,
        is_long: bool
    ) -> pd.Series:
        """
        Computes portfolio weights for selected symbols using specified sizing method.
        Returns a series of weights that sums to 1.0 (will be scaled later if needed).
        """
        n = len(selected_scores)
        if n == 0:
            return pd.Series(dtype=float)
            
        if sizing_method == "EqualWeight":
            return pd.Series(1.0 / n, index=selected_scores.index)
            
        elif sizing_method == "RankWeight":
            # Rank weights: higher scores get higher weights (if long) or lower scores get higher short weight
            # Sort scores
            sorted_scores = selected_scores.sort_values(ascending=not is_long)
            # Ranks: 1 to n (1 is lowest weight, n is highest weight)
            ranks = np.arange(1, n + 1)
            total_rank = ranks.sum()
            weights = ranks / total_rank
            return pd.Series(weights, index=sorted_scores.index)
            
        elif sizing_method == "MarketCapWeight":
            # Proxy market cap weight using dollar volume = Close * Volume
            dollar_vol = price_row[selected_scores.index] * vol_row[selected_scores.index]
            total_vol = dollar_vol.sum()
            if total_vol > 0:
                weights = dollar_vol / total_vol
            else:
                weights = pd.Series(1.0 / n, index=selected_scores.index)
            return weights
            
        else:
            logger.warning(f"Unknown sizing method '{sizing_method}'. Defaulting to EqualWeight.")
            return pd.Series(1.0 / n, index=selected_scores.index)
