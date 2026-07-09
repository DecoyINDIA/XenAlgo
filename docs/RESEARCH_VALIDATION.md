# Research Validation

This repo now includes a first-class offline walk-forward validation harness for promoted
research alphas.

The harness lives in `Brain.walk_forward` and is deliberately research-only:

- It never imports or calls Dhan broker code.
- It never places, modifies, or cancels orders.
- It reuses `PortfolioEngine` for point-in-time target weights.
- It reuses `BacktestEngine` so transaction costs and slippage come from the existing
  research cost model.
- It creates anchored expanding train windows followed by out-of-sample test windows.

## Minimal usage

```python
from Brain.walk_forward import WalkForwardValidator

report = WalkForwardValidator(config).run(
    factor_scores,
    panel,
    train_bars=252 * 3,
    test_bars=252,
)

print(report.as_dict()["aggregate"])
```

`factor_scores` is the daily alpha score DataFrame and `panel` is the usual OHLCV panel
dictionary with `open`, `high`, `low`, `close`, and `volume` frames.

## What the report contains

Each window reports:

- final value,
- total return,
- annualized volatility,
- Sharpe,
- max drawdown,
- trade count,
- gross notional,
- transaction costs,
- cost drag.

The aggregate report summarizes window count, total out-of-sample bars, mean Sharpe,
median test-window return, worst drawdown, total trades, and total transaction costs.

## Boundary

This is the validation harness, not validation evidence by itself. Before live capital,
the operator still needs real dated reports for `std30`, `alpha_027`, and `alpha_062`
against the intended universe, costs, slippage assumptions, and market-data snapshot.
