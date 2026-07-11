# Phase 3.4 Operations Runbook

Phase 3.4 is the go-live checklist gate for the first live-capital stage. It happens only
after Phase 3.1, Phase 3.2, and Phase 3.3 evidence has passed. The allowed initial blast
radius is 10% capital. Anything larger belongs to Phase 3.5 staged ramp.

This repository includes `xenalgo.phase34` to evaluate supplied evidence. The module does
does not call Fyers, read secrets, mutate config, or place/modify/cancel live orders.

## Required Evidence

Record one non-secret checklist row:

```csv
activated_at,live_host_id,config_checksum,phase0_foundation_passed,phase1_execution_core_passed,phase2_console_passed,phase31_failure_injection_passed,phase32_burn_in_passed,phase32_live_host_readiness_passed,phase33_post_migration_passed,static_ip_verified_at,token_refresh_sessions,backup_restore_drill_at,local_kill_switch_verified_at,session_revocation_verified_at,phone_alerts_confirmed_at,dedicated_account_funded,operator_approval_id,live_trading_enabled,broker_order_api_enabled,live_trading_mode,capital_fraction,governor_max_orders_per_sec
2026-08-16T08:00:00,aws-mumbai-live-1,sha256:<checksum>,true,true,true,true,true,true,true,2026-08-15T08:00:00,5,2026-08-14,2026-08-15T10:00:00,2026-08-15T10:15:00,2026-08-15T10:30:00,true,approval-2026-08-16,true,true,live,0.10,2
```

Pass conditions encoded in `GoLiveChecklistReview`:

- G0, G1, G2, Phase 3.1, Phase 3.2 burn-in, Phase 3.2 live-host readiness, and Phase 3.3
  post-migration evidence have all passed.
- Live host id and go-live config checksum are recorded.
- Static IP startup verification happened before activation.
- At least 5 token-refresh sessions are evidenced.
- Backup/restore drill, XenAlgo's local kill path, Fyers session revocation, and real-phone
  alerts are verified before activation.
- Dedicated Fyers account is funded and explicit operator approval is recorded.
- Initial live capital fraction is greater than 0 and no more than 10%.
- Governor order rate remains at or below 2 orders/sec.
- Activation is recorded outside NSE market hours.
- For activation review, `live_trading.enabled=true`,
  `broker.order_api_enabled=true`, and `live_trading.mode=live`.

Use this as a pre-activation checklist while live flags are still off:

```powershell
./_source/.venv/Scripts/python.exe - <<'PY'
from xenalgo.phase34 import GoLiveChecklistReview, load_go_live_checklist_csv

summary = GoLiveChecklistReview().evaluate(
    load_go_live_checklist_csv("Diary/burnin/phase34.csv"),
    require_activation=False,
)
print(summary)
raise SystemExit(0 if summary.passed else 1)
PY
```

Use activation review only after the operator has separately approved enabling the live
config at the 10% stage:

```powershell
./_source/.venv/Scripts/python.exe - <<'PY'
from xenalgo.phase34 import GoLiveChecklistReview, load_go_live_checklist_csv

summary = GoLiveChecklistReview().evaluate(load_go_live_checklist_csv("Diary/burnin/phase34.csv"))
print(summary)
raise SystemExit(0 if summary.passed else 1)
PY
```

Keep `Diary/` out of git; commit only summarized, non-secret evidence if the operator
decides it belongs in docs.
