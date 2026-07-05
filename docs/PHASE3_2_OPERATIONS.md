# Phase 3.2 Operations Runbook

Phase 3.2 is an evidence gate, not a local-only code milestone. It has two parts:

- Phase 3.2a: at least four calendar weeks of paper burn-in on live market data.
- Phase 3.2b: paid live-host migration readiness before any live capital is enabled.

This repository now includes `xenalgo.phase32` to evaluate supplied evidence. The module does
not call Dhan, read secrets, register IPs, deploy hosts, or enable live trading.

## Burn-In Evidence

Record one row per sleeve per trading day:

```csv
trading_date,sleeve,paper_return,backtest_return,token_refresh_ok,safety_incidents,unexplained_outlier,notes
2026-07-06,std30,0.0100,0.0110,true,0,false,clean
2026-07-06,alpha_027,0.0040,0.0035,true,0,false,clean
2026-07-06,alpha_062,-0.0020,-0.0025,true,0,false,clean
```

Pass conditions encoded in `BurnInReview`:

- Burn-in spans at least 28 calendar days.
- At least 18 reviewed live-market trading days are present.
- Every reviewed day has all three sleeve reviews.
- At least 90% of sleeve-days are within absolute daily tolerance, default `0.005`.
- No safety incidents are recorded.
- No unexplained outlier remains open.
- Token refresh succeeds for every recorded session.

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

- live host provider selected: AWS Mumbai (`ap-south-1`) or DO Bangalore,
- primary and secondary static IPs registered with Dhan at least seven days before go-live,
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
