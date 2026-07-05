import os
import json
import logging
import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("QuantPlatform.ReportGenerator")

# Configure Plotly to generate standalone HTML files
pio.templates.default = "plotly_dark"

class ReportGenerator:
    """
    Computes performance metrics, compiles trade statistics, generates interactive Plotly
    charts, and outputs HTML, Markdown, and JSON summary reports.
    """
    def __init__(self, config: dict):
        self.config = config
        self.results_dir = "Diary/reports"
        os.makedirs(self.results_dir, exist_ok=True)

    def generate_report(
        self,
        alpha_name: str,
        backtest_results: Dict[str, Any],
        factor_scores: pd.DataFrame,
        panel: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """
        Main entry point to calculate metrics, generate plots, and write report files.
        """
        logger.info(f"Generating reports for alpha: {alpha_name}...")
        
        history_df = backtest_results["history"]
        trades_df = backtest_results["trades"]
        
        # 1. Analyze Trades & Match roundtrips to calculate average cost stats
        trade_stats = self._analyze_trades(trades_df)
        
        # 2. Compute Performance Metrics
        metrics = self._calculate_metrics(history_df, trades_df, trade_stats, factor_scores, panel)
        
        # 3. Create Plots (Plotly HTML strings)
        plots = self._generate_plots(history_df, alpha_name)
        
        # 4. Generate Monthly Returns Heatmap
        monthly_returns_table = self._generate_monthly_returns_table(history_df)
        
        # 5. Save Output Files
        # Create directories for specific alpha
        alpha_dir = os.path.join(self.results_dir, alpha_name)
        os.makedirs(alpha_dir, exist_ok=True)
        
        # Save CSVs
        history_df.to_csv(os.path.join(alpha_dir, "daily_returns.csv"))
        trades_df.to_csv(os.path.join(alpha_dir, "trade_log.csv"))
        
        # Save Summary JSON
        summary_json = {
            "alpha_name": alpha_name,
            "run_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": metrics,
            "monthly_returns": monthly_returns_table.to_dict()
        }
        with open(os.path.join(alpha_dir, "summary.json"), "w") as f:
            json.dump(summary_json, f, indent=4)
            
        # Save Markdown Report
        md_content = self._generate_markdown_report(alpha_name, metrics, monthly_returns_table)
        with open(os.path.join(alpha_dir, "summary.md"), "w") as f:
            f.write(md_content)
            
        # Save Standalone HTML Dashboard Report
        html_content = self._generate_html_report(alpha_name, metrics, monthly_returns_table, plots, trades_df)
        with open(os.path.join(alpha_dir, "report.html"), "w") as f:
            f.write(html_content)
            
        logger.info(f"Report generation complete for {alpha_name}. Saved in: {alpha_dir}")
        return metrics

    def _analyze_trades(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyzes the trade log using average-cost tracking to compute FIFO-like PnL.
        """
        stats = {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "total_brokerage_costs": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "max_win": 0.0,
            "max_loss": 0.0
        }
        
        if trades_df.empty:
            return stats
            
        stats["total_brokerage_costs"] = float(trades_df["costs"].sum())
        
        # Average-cost matching algorithm
        avg_costs = {}   # symbol -> avg_price
        shares_held = {} # symbol -> count
        realized_pnls = []
        
        for _, row in trades_df.iterrows():
            sym = row["symbol"]
            action = row["action"]
            shares = int(row["shares"])
            price = float(row["price"])
            costs = float(row["costs"])
            
            curr_shares = shares_held.get(sym, 0)
            curr_avg = avg_costs.get(sym, 0.0)
            
            if action == "BUY":
                    # Accumulate position
                    new_shares = curr_shares + shares
                    new_avg = (curr_shares * curr_avg + shares * price) / new_shares if new_shares > 0 else 0.0
                    shares_held[sym] = new_shares
                    avg_costs[sym] = new_avg
            else:
                # Sell order — closing long position
                    closed_shares = min(curr_shares, shares)
                    pnl = closed_shares * (price - curr_avg) - (costs * (closed_shares / shares))
                    realized_pnls.append(pnl)
                    
                    # Update shares remaining
                    shares_held[sym] = curr_shares - shares
                    if shares_held[sym] == 0:
                        avg_costs[sym] = 0.0
                    
        # Summarize realized trade PnLs
        if len(realized_pnls) > 0:
            pnls = np.array(realized_pnls)
            wins = pnls[pnls > 0]
            losses = pnls[pnls <= 0]
            
            stats["total_trades"] = len(pnls)
            stats["winning_trades"] = len(wins)
            stats["losing_trades"] = len(losses)
            stats["win_rate"] = float(len(wins) / len(pnls)) if len(pnls) > 0 else 0.0
            stats["avg_profit"] = float(wins.mean()) if len(wins) > 0 else 0.0
            stats["avg_loss"] = float(losses.mean()) if len(losses) > 0 else 0.0
            stats["max_win"] = float(wins.max()) if len(wins) > 0 else 0.0
            stats["max_loss"] = float(losses.min()) if len(losses) > 0 else 0.0
            
            total_gain = float(wins.sum())
            total_loss = float(abs(losses.sum()))
            stats["profit_factor"] = total_gain / total_loss if total_loss > 0 else (total_gain if total_gain > 0 else 1.0)
            
        return stats

    def _calculate_metrics(
        self,
        history_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        trade_stats: Dict[str, Any],
        factor_scores: pd.DataFrame,
        panel: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """
        Calculates performance and risk metrics on the portfolio equity history.
        """
        daily_returns = history_df["returns"]
        benchmark_returns = history_df.get("benchmark_returns", daily_returns * 0.0)
        
        n_days = len(daily_returns)
        if n_days == 0:
            return {}
            
        # Total Return & CAGR
        initial_val = self.config["backtest"]["initial_capital"]
        final_val = history_df["portfolio_value"].iloc[-1]
        total_return = (final_val / initial_val) - 1.0
        
        years = n_days / 252.0
        cagr = (final_val / initial_val) ** (1.0 / years) - 1.0 if years > 0 and final_val > 0 else 0.0
        
        # Volatility & Sharpe
        daily_vol = daily_returns.std()
        ann_vol = daily_vol * np.sqrt(252)
        
        mean_daily_ret = daily_returns.mean()
        sharpe = (mean_daily_ret / daily_vol) * np.sqrt(252) if daily_vol > 0 else 0.0
        
        # Sortino
        neg_returns = daily_returns[daily_returns < 0]
        downside_std = neg_returns.std()
        sortino = (mean_daily_ret / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0
        
        # Drawdowns & Recovery
        equity_curve = history_df["portfolio_value"]
        running_max = equity_curve.cummax()
        drawdowns = (equity_curve / running_max) - 1.0
        max_drawdown = drawdowns.min()
        
        # Recovery time calculation
        drawdown_days = 0
        max_recovery_days = 0
        in_drawdown = False
        peak_idx = 0
        
        for idx, dd in enumerate(drawdowns):
            if dd < 0:
                drawdown_days += 1
                if not in_drawdown:
                    in_drawdown = True
            else:
                if in_drawdown:
                    max_recovery_days = max(max_recovery_days, drawdown_days)
                    drawdown_days = 0
                    in_drawdown = False
        max_recovery_days = max(max_recovery_days, drawdown_days)
        
        # Calmar
        calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0
        
        # Information Ratio (Benchmark Active Return)
        active_returns = daily_returns - benchmark_returns
        active_risk = active_returns.std() * np.sqrt(252)
        ann_active_return = active_returns.mean() * 252
        information_ratio = ann_active_return / active_risk if active_risk > 0 else 0.0
        
        # Turnover: total traded / average portfolio value
        avg_port_value = history_df["portfolio_value"].mean()
        total_traded = trades_df["value"].sum() if not trades_df.empty else 0.0
        turnover = total_traded / avg_port_value if avg_port_value > 0 else 0.0
        
        # Rank Information Coefficient (IC) & Alpha Decay
        ic_mean, ic_ir = self._calculate_rank_ic(factor_scores, panel)
        alpha_decay = self._calculate_alpha_decay(factor_scores, panel)
        
        metrics = {
            "total_return": float(total_return),
            "cagr": float(cagr),
            "volatility": float(ann_vol),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "calmar_ratio": float(calmar),
            "max_drawdown": float(max_drawdown),
            "recovery_days": int(max_recovery_days),
            "information_ratio": float(information_ratio),
            "turnover": float(turnover),
            "daily_win_rate": float(daily_returns[daily_returns > 0].count() / daily_returns[daily_returns != 0].count()) if daily_returns[daily_returns != 0].count() > 0 else 0.0,
            "rank_ic_mean": float(ic_mean),
            "rank_ic_ir": float(ic_ir),
            "alpha_decay_1d": float(alpha_decay.get(1, 0.0)),
            "alpha_decay_5d": float(alpha_decay.get(5, 0.0)),
            "alpha_decay_10d": float(alpha_decay.get(10, 0.0)),
            **trade_stats
        }
        
        return metrics

    def _calculate_rank_ic(self, factor_scores: pd.DataFrame, panel: Dict[str, pd.DataFrame]) -> Tuple[float, float]:
        """
        Calculates Rank Information Coefficient (Spearman correlation between factors at t-1 and returns t)
        """
        close_df = panel["close"]
        daily_returns = close_df.pct_change(fill_method=None).shift(-1) # forward 1 day return
        
        # Calculate daily spearman correlations
        daily_ics = []
        for date in factor_scores.index:
            if date not in daily_returns.index:
                continue
            f_scores = factor_scores.loc[date]
            f_rets = daily_returns.loc[date]
            
            valid_mask = f_scores.notna() & f_rets.notna()
            if valid_mask.sum() > 10: # Min stocks to calculate correlation
                # Spearman rank correlation
                ic = f_scores[valid_mask].corr(f_rets[valid_mask], method='spearman')
                if not pd.isna(ic):
                    daily_ics.append(ic)
                    
        if len(daily_ics) == 0:
            return 0.0, 0.0
            
        ics = np.array(daily_ics)
        mean_ic = ics.mean()
        std_ic = ics.std()
        
        # Information Ratio of IC = Mean IC / Std IC
        ic_ir = mean_ic / std_ic if std_ic > 0 else 0.0
        return mean_ic, ic_ir

    def _calculate_alpha_decay(self, factor_scores: pd.DataFrame, panel: Dict[str, pd.DataFrame]) -> Dict[int, float]:
        """
        Calculates the decay of alpha scores by computing correlation with future k-day returns.
        """
        close_df = panel["close"]
        decay = {}
        
        for k in [1, 5, 10]:
            # Forward k-day return
            fwd_returns = close_df.pct_change(periods=k, fill_method=None).shift(-k)
            
            daily_ics = []
            for date in factor_scores.index:
                if date not in fwd_returns.index:
                    continue
                f_scores = factor_scores.loc[date]
                f_rets = fwd_returns.loc[date]
                
                valid_mask = f_scores.notna() & f_rets.notna()
                if valid_mask.sum() > 10:
                    ic = f_scores[valid_mask].corr(f_rets[valid_mask], method='spearman')
                    if not pd.isna(ic):
                        daily_ics.append(ic)
            
            decay[k] = np.mean(daily_ics) if len(daily_ics) > 0 else 0.0
            
        return decay

    def _generate_monthly_returns_table(self, history_df: pd.DataFrame) -> pd.DataFrame:
        """
        Pivots daily returns into a Monthly/Yearly returns table.
        """
        daily_ret = history_df["returns"].copy()
        
        # Group by year and month, compound returns
        monthly_ret = daily_ret.groupby([daily_ret.index.year, daily_ret.index.month]).apply(lambda r: (1.0 + r).prod() - 1.0)
        
        # Unstack into year rows and month columns
        monthly_table = monthly_ret.unstack(level=1)
        monthly_table = monthly_table.reindex(columns=range(1, 13))
        monthly_table.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Add Yearly compounded total return
        yearly_total = daily_ret.groupby(daily_ret.index.year).apply(lambda r: (1.0 + r).prod() - 1.0)
        monthly_table['Yearly'] = yearly_total
        
        return np.round(monthly_table * 100, 2)

    def _generate_plots(self, history_df: pd.DataFrame, alpha_name: str) -> Dict[str, str]:
        """
        Generates Plotly interactive HTML plots and returns them as HTML strings.
        """
        plots = {}
        
        # 1. Equity Curve Chart
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(
            x=history_df.index, y=history_df["equity_curve"],
            mode='lines', name='Strategy Equity',
            line=dict(color='#00ffcc', width=2)
        ))
        if "benchmark_curve" in history_df.columns:
            fig_equity.add_trace(go.Scatter(
                x=history_df.index, y=history_df["benchmark_curve"],
                mode='lines', name='Benchmark',
                line=dict(color='#ff5555', width=1.5, dash='dash')
            ))
            
        fig_equity.update_layout(
            title=f"Equity Curve - {alpha_name}",
            xaxis_title="Date",
            yaxis_title="Normalized Value",
            legend=dict(x=0, y=1),
            margin=dict(l=40, r=40, t=50, b=40),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=True, gridcolor='#333'),
            yaxis=dict(showgrid=True, gridcolor='#333')
        )
        plots["equity_curve"] = pio.to_html(fig_equity, full_html=False, include_plotlyjs='cdn')
        
        # 2. Drawdown Chart
        equity_curve = history_df["portfolio_value"]
        running_max = equity_curve.cummax()
        drawdowns = (equity_curve / running_max) - 1.0
        
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=drawdowns.index, y=drawdowns * 100,
            fill='tozeroy', mode='lines', name='Drawdown',
            line=dict(color='#ff3333', width=1.5),
            fillcolor='rgba(255, 51, 51, 0.2)'
        ))
        fig_dd.update_layout(
            title="Portfolio Drawdown (%)",
            xaxis_title="Date",
            yaxis_title="Drawdown (%)",
            margin=dict(l=40, r=40, t=50, b=40),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=True, gridcolor='#333'),
            yaxis=dict(showgrid=True, gridcolor='#333')
        )
        plots["drawdown_curve"] = pio.to_html(fig_dd, full_html=False, include_plotlyjs='cdn')
        
        # 3. Rolling Sharpe (6 Month = 126 trading days)
        rolling_days = 126
        if len(history_df) > rolling_days:
            rolling_sharpe = history_df["returns"].rolling(window=rolling_days).apply(
                lambda r: (r.mean() / r.std()) * np.sqrt(252) if r.std() > 0 else 0.0
            )
            fig_sharpe = go.Figure()
            fig_sharpe.add_trace(go.Scatter(
                x=rolling_sharpe.index, y=rolling_sharpe,
                mode='lines', name='6m Rolling Sharpe',
                line=dict(color='#ffaa00', width=1.5)
            ))
            fig_sharpe.update_layout(
                title="6-Month Rolling Sharpe Ratio",
                xaxis_title="Date",
                yaxis_title="Sharpe Ratio",
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=True, gridcolor='#333'),
                yaxis=dict(showgrid=True, gridcolor='#333')
            )
            plots["rolling_sharpe"] = pio.to_html(fig_sharpe, full_html=False, include_plotlyjs='cdn')
        else:
            plots["rolling_sharpe"] = "<p class='no-data'>Insufficient data for 6-Month Rolling Sharpe Chart.</p>"
            
        return plots

    def _generate_markdown_report(self, alpha_name: str, metrics: Dict[str, Any], monthly_table: pd.DataFrame) -> str:
        """
        Creates a clean markdown report of the alpha run.
        """
        return f"""# Backtest Report: {alpha_name}
Run Date: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Performance Summary

| Metric | Strategy Value |
| :--- | :--- |
| **Total Return** | {metrics['total_return']*100:.2f}% |
| **CAGR** | {metrics['cagr']*100:.2f}% |
| **Annualized Volatility** | {metrics['volatility']*100:.2f}% |
| **Sharpe Ratio** | {metrics['sharpe_ratio']:.2f} |
| **Sortino Ratio** | {metrics['sortino_ratio']:.2f} |
| **Calmar Ratio** | {metrics['calmar_ratio']:.2f} |
| **Max Drawdown** | {metrics['max_drawdown']*100:.2f}% |
| **Recovery Period** | {metrics['recovery_days']} days |
| **Information Ratio** | {metrics['information_ratio']:.2f} |
| **Turnover** | {metrics['turnover']*100:.1f}% |
| **Daily Win Rate** | {metrics['daily_win_rate']*100:.2f}% |

## Trade Statistics

| Statistic | Value |
| :--- | :--- |
| **Total Closed Trades** | {metrics['total_trades']} |
| **Trade Win Rate** | {metrics['win_rate']*100:.2f}% |
| **Average Profit per Winning Trade** | INR {metrics['avg_profit']:,.2f} |
| **Average Loss per Losing Trade** | INR {metrics['avg_loss']:,.2f} |
| **Profit Factor** | {metrics['profit_factor']:.2f} |
| **Total Brokerage & Taxes Paid** | INR {metrics['total_brokerage_costs']:,.2f} |
| **Max Win / Max Loss** | INR {metrics['max_win']:,.2f} / INR {metrics['max_loss']:,.2f} |

## Alpha Diagnostics

| Metric | Value |
| :--- | :--- |
| **Mean Rank IC** | {metrics['rank_ic_mean']:.4f} |
| **Information Coefficient IR** | {metrics['rank_ic_ir']:.2f} |
| **Alpha Decay Correlation (1d / 5d / 10d)** | {metrics['alpha_decay_1d']:.4f} / {metrics['alpha_decay_5d']:.4f} / {metrics['alpha_decay_10d']:.4f} |

## Monthly Returns (%)

{monthly_table.to_markdown()}
"""

    def _generate_html_report(
        self,
        alpha_name: str,
        metrics: Dict[str, Any],
        monthly_table: pd.DataFrame,
        plots: Dict[str, str],
        trades_df: pd.DataFrame
    ) -> str:
        """
        Builds a state-of-the-art interactive HTML dashboard report.
        """
        # Convert monthly returns table to HTML
        monthly_html = monthly_table.to_html(classes="table-monthly")
        
        # Build trade list rows
        trade_rows = ""
        if not trades_df.empty:
            # Show up to 100 recent trades for size efficiency in report
            limit_trades = trades_df.tail(100)
            for _, row in limit_trades.iterrows():
                flow_class = "flow-green" if row["net_cash_flow"] > 0 else "flow-red"
                trade_rows += f"""
                <tr>
                    <td>{row['date'].strftime('%Y-%m-%d')}</td>
                    <td>{row['symbol']}</td>
                    <td><span class="badge {row['action']}">{row['action']}</span></td>
                    <td>{int(row['shares']):,}</td>
                    <td>INR {row['price']:,.2f}</td>
                    <td>INR {row['costs']:,.2f}</td>
                    <td><span class="{flow_class}">INR {row['net_cash_flow']:,.2f}</span></td>
                </tr>
                """
        else:
            trade_rows = "<tr><td colspan='7'>No trades executed during this run.</td></tr>"
            
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantPlatform Dashboard - {alpha_name}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0f111a;
            --card-bg: #151824;
            --border-color: #24293e;
            --text-color: #e2e8f0;
            --text-muted: #64748b;
            --accent-neon: #00ffcc;
            --long-color: #10b981;
            --short-color: #ef4444;
            --font-main: 'Outfit', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: var(--font-main);
            margin: 0;
            padding: 0;
        }}
        
        .header {{
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border-color);
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .header h1 {{
            margin: 0;
            font-weight: 800;
            font-size: 1.8rem;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff 0%, var(--accent-neon) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .header .meta {{
            font-family: var(--font-mono);
            color: var(--text-muted);
            font-size: 0.85rem;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 40px;
        }}
        
        .grid-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .card-stat {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s, border-color 0.2s;
        }}
        
        .card-stat:hover {{
            transform: translateY(-2px);
            border-color: var(--accent-neon);
        }}
        
        .card-stat .label {{
            color: var(--text-muted);
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        
        .card-stat .value {{
            font-size: 1.8rem;
            font-weight: 800;
        }}
        
        .card-stat .value.positive {{ color: var(--long-color); }}
        .card-stat .value.negative {{ color: var(--short-color); }}
        
        .grid-charts {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        .chart-box {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }}
        
        .grid-tables {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        .table-box {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            overflow-x: auto;
        }}
        
        .table-box h3 {{
            margin-top: 0;
            margin-bottom: 20px;
            font-weight: 600;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
        }}
        
        .table-monthly table {{
            width: 100%;
            border-collapse: collapse;
            font-family: var(--font-mono);
            font-size: 0.9rem;
        }}
        
        .table-monthly th, .table-monthly td {{
            padding: 10px;
            text-align: right;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .table-monthly th {{
            color: var(--text-muted);
            font-weight: 600;
        }}
        
        .table-monthly tr:hover {{
            background-color: rgba(255,255,255,0.02);
        }}
        
        .table-monthly td:last-child, .table-monthly th:last-child {{
            font-weight: 800;
            border-left: 1px solid var(--border-color);
        }}
        
        .badge {{
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 800;
            font-family: var(--font-mono);
        }}
        .badge.BUY {{ background-color: rgba(16, 185, 129, 0.2); color: var(--long-color); }}
        .badge.SELL {{ background-color: rgba(239, 68, 68, 0.2); color: var(--short-color); }}
        
        .flow-green {{ color: var(--long-color); font-family: var(--font-mono); }}
        .flow-red {{ color: var(--short-color); font-family: var(--font-mono); }}
        
        .trades-list-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        
        .trades-list-table th, .trades-list-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .trades-list-table th {{
            color: var(--text-muted);
        }}
        
        .scrollable-table {{
            max-height: 400px;
            overflow-y: auto;
        }}
        
        .no-data {{
            color: var(--text-muted);
            text-align: center;
            font-style: italic;
            padding: 40px;
        }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>Alpha Backtest Report: {alpha_name}</h1>
            <div style="color: var(--text-muted); font-size: 0.9rem; margin-top: 5px;">Institutional-Grade Factor Strategy Performance Review</div>
        </div>
        <div class="meta">
            Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>

    <div class="container">
        
        <!-- Performance Statistics Row -->
        <div class="grid-stats">
            <div class="card-stat">
                <div class="label">Total Return</div>
                <div class="value positive">{metrics['total_return']*100:.2f}%</div>
            </div>
            <div class="card-stat">
                <div class="label">Annual Return (CAGR)</div>
                <div class="value positive">{metrics['cagr']*100:.2f}%</div>
            </div>
            <div class="card-stat">
                <div class="label">Sharpe Ratio</div>
                <div class="value" style="color: #ffaa00;">{metrics['sharpe_ratio']:.2f}</div>
            </div>
            <div class="card-stat">
                <div class="label">Max Drawdown</div>
                <div class="value negative">{metrics['max_drawdown']*100:.2f}%</div>
            </div>
            <div class="card-stat">
                <div class="label">Trade Win Rate</div>
                <div class="value">{metrics['win_rate']*100:.1f}%</div>
            </div>
            <div class="card-stat">
                <div class="label">Profit Factor</div>
                <div class="value" style="color: var(--accent-neon);">{metrics['profit_factor']:.2f}</div>
            </div>
        </div>

        <!-- Charts Grid -->
        <div class="grid-charts">
            <div class="chart-box">
                {plots['equity_curve']}
            </div>
            <div class="chart-box">
                {plots['drawdown_curve']}
            </div>
        </div>
        
        <div style="margin-bottom: 40px;">
            <div class="chart-box">
                {plots['rolling_sharpe']}
            </div>
        </div>

        <!-- Tables Row -->
        <div class="grid-tables">
            <!-- Monthly Returns Table -->
            <div class="table-box">
                <h3>Monthly Returns Heatmap (%)</h3>
                <div class="table-monthly">
                    {monthly_html}
                </div>
            </div>
            
            <!-- Trade Log Table (recent 100) -->
            <div class="table-box">
                <h3>Recent Executed Trades (Last 100)</h3>
                <div class="scrollable-table">
                    <table class="trades-list-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Symbol</th>
                                <th>Action</th>
                                <th>Shares</th>
                                <th>Execution Px</th>
                                <th>Costs</th>
                                <th>Net Cash Flow</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trade_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Factor Analysis Table -->
        <div class="table-box" style="margin-top: 20px;">
            <h3>Alpha Diagnostic & Prediction Performance</h3>
            <table class="trades-list-table" style="width: 100%;">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                        <th>Interpretation</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Mean Rank Information Coefficient (IC)</strong></td>
                        <td style="font-family: var(--font-mono); font-weight: bold;">{metrics['rank_ic_mean']:.4f}</td>
                        <td>Spearman rank correlation between signal and subsequent 1-day stock return. >0.02 is significant.</td>
                    </tr>
                    <tr>
                        <td><strong>IC Information Ratio (IC IR)</strong></td>
                        <td style="font-family: var(--font-mono); font-weight: bold;">{metrics['rank_ic_ir']:.2f}</td>
                        <td>Mean IC divided by standard deviation of IC. Measures prediction consistency. >1.0 is highly stable.</td>
                    </tr>
                    <tr>
                        <td><strong>Alpha Decay (1-Day Forward Correlation)</strong></td>
                        <td style="font-family: var(--font-mono); font-weight: bold;">{metrics['alpha_decay_1d']:.4f}</td>
                        <td>Predictive correlation for a 1-day holding horizon.</td>
                    </tr>
                    <tr>
                        <td><strong>Alpha Decay (5-Day Forward Correlation)</strong></td>
                        <td style="font-family: var(--font-mono); font-weight: bold;">{metrics['alpha_decay_5d']:.4f}</td>
                        <td>Predictive correlation for a 5-day holding horizon (Weekly rebalance decay).</td>
                    </tr>
                    <tr>
                        <td><strong>Alpha Decay (10-Day Forward Correlation)</strong></td>
                        <td style="font-family: var(--font-mono); font-weight: bold;">{metrics['alpha_decay_10d']:.4f}</td>
                        <td>Predictive correlation for a 10-day holding horizon.</td>
                    </tr>
                </tbody>
            </table>
        </div>

    </div>

</body>
</html>
"""
        return html
