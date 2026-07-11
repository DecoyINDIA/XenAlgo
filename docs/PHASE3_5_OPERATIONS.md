# Phase 3.5 Operations Runbook

Phase 3.5 is the staged live-capital ramp after the Phase 3.4 go-live checklist has passed
and the separately approved 10% live stage is active. The required sequence is:

```text
10% -> 25% -> 50% -> 100%
```

Each stage must run for at least two clean calendar weeks before the next increase. This
repository includes `xenalgo.phase35` to evaluate supplied evidence. The module does not
call Fyers, read secrets, mutate config, place orders, cancel orders, or approve capital
increases.

## Prerequisite Evidence

Record these non-secret facts before evaluating ramp records:

- Phase 3.4 go-live evidence has passed.
- Live host id.
- Initial approved capital fraction is `0.10`.

Phase 3.5 starts from the approved 10% live-capital stage. Any attempt to start from a
larger fraction fails closed.

## Ramp Evidence

Record one row per sleeve per trading day:

```csv
stage,capital_fraction,stage_started_at,stage_ended_at,trading_date,sleeve,live_return,backtest_return,live_host_id,config_checksum,operator_approval_id,governor_max_orders_per_sec,safety_incidents,reconciliation_clean,compensating_kill_controls_armed,unexplained_outlier,notes
10%,0.10,2026-08-16T08:00:00,2026-08-29T18:00:00,2026-08-17,std30,0.0100,0.0110,aws-mumbai-live-1,sha256:<checksum>,approval-10,2,0,true,true,false,clean
10%,0.10,2026-08-16T08:00:00,2026-08-29T18:00:00,2026-08-17,alpha_027,0.0040,0.0035,aws-mumbai-live-1,sha256:<checksum>,approval-10,2,0,true,true,false,clean
10%,0.10,2026-08-16T08:00:00,2026-08-29T18:00:00,2026-08-17,alpha_062,-0.0020,-0.0025,aws-mumbai-live-1,sha256:<checksum>,approval-10,2,0,true,true,false,clean
```

Pass conditions encoded in `CapitalRampReview`:

- Phase 3.4 go-live evidence has passed first.
- Stages are exactly `10% -> 25% -> 50% -> 100%`.
- Each stage has one consistent start/end window, capital fraction, config checksum, and
  operator approval id.
- Each stage spans at least 14 calendar days and at least 10 reviewed trading days.
- Every reviewed trading day has all three sleeve reviews.
- Stages do not overlap.
- Stage activation and completion are recorded outside NSE market hours.
- Every record is from the expected live host.
- Governor order rate remains at or below 2 orders/sec.
- At least 90% of sleeve-days are within absolute daily tolerance, default `0.005`.
- No safety incidents, reconciliation failures, compensating kill-control gaps, or
  unexplained outliers are recorded.

Use this as a local evidence check:

```powershell
./_source/.venv/Scripts/python.exe - <<'PY'
from xenalgo.phase35 import (
    CapitalRampReview,
    RampPrerequisiteEvidence,
    load_ramp_csv,
)

summary = CapitalRampReview().evaluate(
    load_ramp_csv("Diary/burnin/phase35.csv"),
    RampPrerequisiteEvidence(
        phase34_go_live_passed=True,
        live_host_id="aws-mumbai-live-1",
        initial_capital_fraction=0.10,
    ),
)
print(summary)
raise SystemExit(0 if summary.passed else 1)
PY
```

Keep `Diary/` out of git; commit only summarized, non-secret evidence if the operator
decides it belongs in docs.
