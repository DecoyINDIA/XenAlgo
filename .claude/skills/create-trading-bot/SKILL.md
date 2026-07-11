---
name: create-trading-bot
description: Build a complete XenAlgo trading bot from any trading setup (entry/exit rules, indicator formula, or strategy description). Generates the strategy module, backtest + walk-forward validation, sleeve config, risk wiring, and tests — always in paper mode, never enabling live trading. Use when the user describes a trading setup, strategy idea, alpha formula, or says "create a bot for <setup>", "add strategy", "new alpha", or "/create-trading-bot".
---

# Create Trading Bot from Setup

Turn any trading setup into a fully wired XenAlgo bot: strategy module → validation → sleeve config → tests → paper-mode readiness. The execution/risk/guardrail stack already exists; this skill plugs a new setup into it correctly.

## Hard safety rules (never violate)

1. **Never** set `live_trading.enabled: true` or `broker.order_api_enabled: true` in any config file. New bots always start in `mode: paper`.
2. **Never** bypass or weaken `RiskEngine` (`xenalgo/risk.py`) limits, the governor (`xenalgo/broker/governor.py`), or the phase gates. A strategy proposes; risk disposes.
3. A setup that fails validation (Step 4) does **not** get wired into config. Report the failure honestly and stop.
4. Every generated strategy must be deterministic on daily bars — no lookahead: signals may only use completed bars (the backtester lags signals one day and fills at close; live matches it).

## Step 0 — Parse the setup

Extract from the user's description (ask only if genuinely ambiguous):

| Field | Examples | Default |
|---|---|---|
| Signal logic | "RSI(14) < 30 buy", "20/50 EMA cross", "std of close / close" | required |
| Direction | long-only / long-short rank | long-only |
| Universe | NIFTY-500 (only supported universe today) | NIFTY-500 |
| Frequency | daily (only supported cadence) | 1d |
| Warmup bars | longest lookback in the formula | derive from formula |
| Rebalance | weekly on configured day | weekly |

If the setup needs intraday data, options/F&O, or a non-Dhan broker, stop and tell the user those are explicit v1 non-goals (PLAN.md §1) — offer the closest daily-bar swing equivalent instead.

## Step 1 — Generate the strategy module

Create `Strategies/<setup_id>.py` following the exact pattern of `Strategies/std30.py`:

```python
"""<one-line description of the setup>."""
from __future__ import annotations

import pandas as pd
from Brain.base import safe_div, ts_std  # import only helpers that exist in Brain/base.py

__alpha_meta__ = {
    'id': '<setup_id>',
    'theme': ['<momentum|mean_reversion|volatility|trend|...>'],
    'formula_latex': '<latex>',
    'columns_required': ['close'],   # only columns the formula reads: open/high/low/close/volume
    'universe': ['equity_in'],
    'frequency': ['1d'],
    'decay_horizon': <int>,
    'min_warmup_bars': <longest lookback>,
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return the alpha score on the supplied OHLCV panel (dates x symbols)."""
    ...
```

Rules:
- `compute` takes the panel dict (`panel['close']` etc., each a dates×symbols DataFrame) and returns a **score DataFrame** of the same shape. Higher score = stronger buy candidate. Do not return orders, weights, or positions — ranking/sizing is the engine's job.
- Use vectorized pandas + `Brain.base` helpers (`safe_div`, `ts_std`, and whatever else `Brain/base.py` actually exports — read it first, never invent helpers).
- For rule-style setups (e.g. "buy when RSI < 30"), convert to a continuous score (e.g. `50 - rsi` clipped) so ranking still works; document the conversion in the docstring.
- No I/O, no network, no randomness, no `datetime.now()` inside `compute`.

## Step 2 — Sanity-check the module

Run a quick import + shape check before any backtest:

```
python -c "import importlib; m = importlib.import_module('Strategies.<setup_id>'); print(m.__alpha_meta__['id'])"
```

Then verify on real data: load a small panel slice the same way `Brain/data_manager.py` / existing tests do, call `compute`, and assert: output shape matches input, no all-NaN columns after warmup, values are finite where inputs are finite, and the first `min_warmup_bars` rows are NaN (no lookahead leak).

## Step 3 — Backtest

Run the setup through the existing research engine (`Brain/backtest_engine.py` via `Brain/alpha_engine.py` — read how `std30`/`alpha_027`/`alpha_062` are invoked in `Lab/` or existing tests and mirror it exactly; do not write a parallel backtester). Use the DuckDB panel at the path in `config/config.research.yaml`.

Report at minimum: CAGR, max drawdown, Sharpe, turnover, hit rate, and per-year returns.

## Step 4 — Walk-forward validation (the gate)

Run `Brain/walk_forward.py` on the setup. The bot is only created if the setup survives out-of-sample:

- Positive OOS return in the majority of walk-forward windows.
- OOS Sharpe > 0 and not less than ~50% of in-sample Sharpe (a bigger gap = overfit).
- Max OOS drawdown compatible with the live risk config (`drawdown_halt_pct: 0.10` would halt this bot in paper/live — flag if the backtest DD exceeds it).

**If the setup fails:** stop here. Present the numbers, explain the failure mode (overfit / no edge / drawdown incompatible with guardrails), and suggest parameter or logic variants. Do not wire a failed setup into config "so it exists".

## Step 5 — Wire the bot

Only after Step 4 passes:

1. **Config:** add a sleeve to `config/config.live.yaml` and `config/config.research.yaml` under `sleeves:` with `enabled: false` and a `capital_fraction` that keeps the total ≤ 1.0 (rebalance existing fractions only if the user asks; otherwise take from unallocated headroom or ship at `0.0` and tell the user to allocate). The user flips `enabled: true` deliberately — the skill never auto-enables a sleeve.
2. **Registration:** if the strategy engine discovers sleeves from config only, config is enough; if there's an explicit registry (check `xenalgo/monolith.py` and how the existing three sleeves are located), register the new module the same way.
3. **Tests:** add `tests/unit/test_strategy_<setup_id>.py` mirroring the existing strategy tests: meta contract (required keys present, warmup ≥ longest lookback), shape/NaN/no-lookahead properties from Step 2, and a golden-value check on a tiny fixed panel computed by hand.
4. Run the full suite: `python -m pytest tests/ -q`. Everything must pass.

## Step 6 — Deliverable summary

End with a report the user can act on:

- Setup interpretation (what you took the rules to mean — this catches misparses early).
- Backtest + walk-forward table.
- Files created/modified (linked).
- Current state: **sleeve wired, disabled, paper-mode only.**
- The remaining human path to live, verbatim from the phase gates: enable sleeve in config → paper burn-in per `docs/PHASE0_OPERATIONS.md` and phase 3.x runbooks → operator-approved ramp. The skill's job ends at "validated paper-ready bot"; it never shortens that path.

## Notes

- One invocation = one setup = one sleeve. For multiple setups, run the skill once per setup so each gets its own validation gate.
- If `Brain/base.py` lacks a helper the formula needs (e.g. RSI, EMA), add it to `Brain/base.py` with the same vectorized style and a unit test — don't inline bespoke math in the strategy file.
- Keep the strategy file free of broker, risk, or execution imports. Strategy ↔ execution separation is the licensing and safety boundary (PLAN.md §2).
