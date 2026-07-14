# Phase 3.2 Operations Runbook

Phase 3.2 is an evidence gate, not a local-only code milestone. It has two parts:

- Phase 3.2a: one software commissioning week covering at least five consecutive NSE trading sessions in paper mode on live market data.
- Phase 3.2b: permanent Oracle-host readiness before any live capital is enabled.

This repository now includes `xenalgo.phase32` to evaluate supplied evidence. The module does
does not call Fyers, read secrets, register IPs, deploy hosts, or enable live trading.

## Commissioning Evidence

The strategies already have five-year backtest evidence. This week is not intended to decide
whether a strategy is profitable from five market days. It validates whether the production
software runs unattended and faithfully executes the already-tested strategy logic.

Record one row per sleeve per trading day:

```csv
trading_date,sleeve,paper_return,backtest_return,token_refresh_ok,safety_incidents,reconciliation_clean,session_complete,unresolved_incidents,evidence_checksum,authoritative,unexplained_outlier,notes
2026-07-06,std30,0.0100,0.0110,true,0,true,true,0,sha256:<checksum>,true,false,clean
```

Commissioning pass conditions:

- At least five consecutive expected NSE trading sessions are reviewed.
- Every reviewed day has all three sleeve reviews.
- Scheduling, live-data ingestion, freshness checks, all three strategy runs, risk decisions,
  paper orders, confirmed-fill accounting, reconciliation, journaling, alerts and daily
  summaries complete without an unresolved software failure.
- A controlled restart is recovered safely, without duplicate orders or lost acknowledged
  state.
- Token refresh succeeds across all five sessions.
- The authenticated kill switch halts new submission within one second.
- No safety incidents are recorded.
- No unexplained outlier remains open.
- Paper return and backtest expectation are recorded for observation, but weekly profit or
  loss does not determine whether the software commissioning gate passed.

`BurnInReview` enforces five consecutive expected weekday sessions, all three sleeves,
successful token refresh, clean reconciliation, complete sessions, no unresolved incidents,
and checksummed authoritative evidence. Return deviation is observational, not a pass gate.

Use this as a local evidence check:

```powershell
./_source/.venv/Scripts/python.exe - <<'PY'
from xenalgo.phase32 import BurnInReview, load_burn_in_csv

summary = BurnInReview().evaluate(load_burn_in_csv("Diary/burnin/phase32.csv"))
print(summary)
raise SystemExit(0 if summary.passed else 1)
PY
```

Keep `Diary/` out of git; commit only summarized, non-secret evidence if the operator decides
it belongs in docs.

## Live-Host Evidence

Phase 3.2b requires operator-side proof for:

- permanent Oracle Cloud Always Free host identity and region recorded,
- the static IP configuration required by the activated Fyers order app is registered and verified before go-live,
- same Docker image deployed,
- systemd supervision enabled,
- nightly backups configured,
- successful restore drill completed,
- external heartbeat configured,
- Oracle instance retained as warm dev/staging,
- `live_trading.enabled=false` and `broker.order_api_enabled=false` until the go-live gate.

The readiness checker is intentionally conservative. Passing it means the evidence packet is
internally complete; it does not mean the go-live checklist is complete or that real trading
may be enabled.
