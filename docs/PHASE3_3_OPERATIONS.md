# Phase 3.3 Operations Runbook

Phase 3.3 is the final paper-validation gate on the paid live host. It happens after
Phase 3.2a burn-in and Phase 3.2b live-host migration readiness are complete, and before
any live capital is enabled.

This repository includes `xenalgo.phase33` to evaluate supplied evidence. The module does
not call Dhan, read secrets, register IPs, deploy hosts, or enable live trading.

## Required Host Evidence

Record these non-secret facts for the new live host:

- stable `host_id`,
- provider and approved India region (`ap-south-1`, Mumbai, or Bangalore),
- migration completion date,
- static-IP startup verification date,
- Docker image reference,
- deployed config checksum,
- systemd, backups, and heartbeat enabled,
- Phase 3.2 live-host readiness evidence already passed,
- `live_trading.enabled=false` and `broker.order_api_enabled=false`.

Phase 3.3 is still paper mode. If either live-order flag is enabled, the evidence fails.

## Paper Validation Evidence

Record one row per sleeve per trading day on the new live host:

```csv
validation_date,host_id,sleeve,paper_return,backtest_return,token_refresh_ok,safety_incidents,reconciliation_clean,live_order_api_disabled,unexplained_outlier,notes
2026-08-03,aws-mumbai-live-1,std30,0.0100,0.0110,true,0,true,true,false,clean
2026-08-03,aws-mumbai-live-1,alpha_027,0.0040,0.0035,true,0,true,true,false,clean
2026-08-03,aws-mumbai-live-1,alpha_062,-0.0020,-0.0025,true,0,true,true,false,clean
```

Pass conditions encoded in `PostMigrationValidationReview`:

- validation spans at least 7 calendar days,
- at least 5 reviewed trading days are present,
- every reviewed day has all three sleeve reviews,
- every record is from the expected live host id,
- static IP was startup-verified before validation started,
- at least 90% of sleeve-days are within absolute daily tolerance, default `0.005`,
- token refresh succeeds for at least 5 sessions and has no recorded failures,
- no safety incidents, reconciliation failures, or unexplained outliers are recorded,
- every record confirms the live order API stayed disabled.

Use this as a local evidence check:

```powershell
./_source/.venv/Scripts/python.exe - <<'PY'
import datetime as dt
from xenalgo.phase33 import (
    PostMigrationHostEvidence,
    PostMigrationValidationReview,
    load_post_migration_csv,
)

host = PostMigrationHostEvidence(
    host_id="aws-mumbai-live-1",
    provider="aws",
    region="ap-south-1",
    migrated_at=dt.date(2026, 8, 1),
    static_ip_verified_at=dt.date(2026, 8, 1),
    docker_image_ref="xenalgo:<image-tag>",
    config_checksum="<checksum>",
    systemd_unit_enabled=True,
    backups_configured=True,
    heartbeat_configured=True,
    live_trading_enabled=False,
    broker_order_api_enabled=False,
    phase32_live_host_readiness_passed=True,
)
summary = PostMigrationValidationReview().evaluate(
    load_post_migration_csv("Diary/burnin/phase33.csv"),
    host,
)
print(summary)
raise SystemExit(0 if summary.passed else 1)
PY
```

Keep `Diary/` out of git; commit only summarized, non-secret evidence if the operator
decides it belongs in docs.
