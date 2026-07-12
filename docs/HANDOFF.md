# XenAlgo B0-B6 Engineering Handoff

> Deployment execution status is maintained in [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md).
> Missing credentials and remaining operator evidence are listed without values in
> [DEPLOYMENT_OPERATOR_INPUTS.md](DEPLOYMENT_OPERATOR_INPUTS.md).

**Prepared:** 2026-07-12
**Boundary:** Repository engineering and local release proof only. No Fyers order was placed,
modified, or cancelled. Live-order flags remain false.

## Delivered build

- Fyers-only runtime contract and broker-neutral interfaces:
  `docs/FYERS_CONTRACT.md`, `xenalgo/broker/contracts.py`.
- Injected/mockable OAuth, order gateway, symbol/history, Order WebSocket, REST orderbook,
  cumulative-fill, channel-health, and parity boundaries.
- Concrete-`PaperBroker` production composition that rejects any live gateway injection.
- One owner per journal, engine, broker, listener, reconciler, governor, kill switch, and alert
  bus; deterministic replay and no duplicate intent after restart.
- Startup gates for daily authentication, calendar, config identity, replay, data quality,
  kill/breaker state, and reconciliation.
- Scheduled token/data/startup/reconciliation/execution/EOD/backup/heartbeat job ownership.
- SELL-before-BUY session execution, dynamic risk context, confirmed cumulative paper fills,
  graceful shutdown, and tamper-evident JSON/CSV evidence.
- Phase 3.2 five-consecutive-session evaluator and focused Phase 3.3 parity evaluator.
- Fyers-accurate compensating kill evidence for Phase 3.4/3.5.
- Traceability matrix: `docs/TRACEABILITY.md`.

## Release identity

The completed B0-B6 engineering release is identified by:

| Artifact | Verified identity |
|---|---|
| Git commit | `b8c1913ab7d4ed1391188a809f64c5364e041d98` |
| Local Docker image | `sha256:54970a52679bb0e740c5729af0404e50cae13ec82009255197d9f3f25e57b906` |
| Dependency lock SHA-256 | `D75F46483E8C6387B821035F04C530B8EC18FFE49174976E0C1472AB0F5AAE0D` |
| Live config SHA-256 | `8020b612358e6da269c1964211bb07b524b27450afee35b1b7130a69be407500` |
| Evidence schema | `phase32-session-v2` |

Reproduce those identities from the committed checkout with:

```powershell
git rev-parse HEAD
Get-FileHash requirements.lock -Algorithm SHA256
./_source/.venv/Scripts/python.exe -m xenalgo --profile live
docker build --pull=false -t xenalgo:b0-b6-rc .
docker image inspect xenalgo:b0-b6-rc --format '{{.Id}}'
```

The local image has not been published to a registry, so it has an image ID rather than a
registry `RepoDigest`. Before Oracle deployment, publish it to the approved registry, record
its immutable registry digest, and verify it was built from the commit above. Never deploy
from a mutable tag alone.

## Exact local startup and health commands

```powershell
# Validate both profiles
./_source/.venv/Scripts/python.exe -m xenalgo --profile research
./_source/.venv/Scripts/python.exe -m xenalgo --profile live

# Prove the image is paper-only and state paths are writable
docker run --rm xenalgo:b0-b6-rc
docker run --rm xenalgo:b0-b6-rc python -m xenalgo.paper_daemon --check --root /app

# Private operator console
./_source/.venv/Scripts/python.exe -m xenalgo.web.server --profile live
```

The scheduled daemon is composed through `ProductionPaperDaemon` and
`ScheduledPaperRuntime`. The Oracle service must inject the approved daily-auth, live-data,
strategy-order, backup, and heartbeat callbacks; the concrete broker remains `PaperBroker`.
Do not substitute `FyersGateway` in this composition.

## Non-secret environment manifest

Use `deploy/oracle/xenalgo.env.example` and `.env.example`. Required names include:

- `FYERS_APP_ID`, `FYERS_SECRET_KEY`, `FYERS_REDIRECT_URI`;
- the approved daily-2FA/auth-code input mechanism;
- `TAILSCALE_BIND_HOST`;
- Telegram/Pushover identifiers;
- `XENALGO_IMAGE_DIGEST`;
- static-IP identity variables required by the activated Fyers app.

Values belong in `/etc/xenalgo/xenalgo.env` with least privilege. Never put values in git,
image layers, logs, evidence, or backups. The token store is `.xenalgo-secrets/fyers_token.sqlite`
and must be excluded from backups.

## State, backup, and evidence paths

- Paper journal: `Diary/state/order_journal.sqlite`
- Market data: `Supply/database/market_data.duckdb` (live process read-only)
- Logs: `Diary/logs/`
- Session evidence: operator-selected directory under `Diary/`; JSON plus `phase32.csv`
- Token state: `.xenalgo-secrets/` (excluded from backup)
- Off-box backup: SQLite online backup plus DuckDB/Parquet export; verify with a disposable
  restore before commissioning.

## Deploy and rollback

Follow `docs/DEPLOYMENT_PLAN.md` D0-D5. Deploy only outside NSE market hours. Pin the final
image by digest, mount dedicated paper state, validate config, start the scheduled daemon and
private console, then verify heartbeat, replay, reconciliation, evidence creation, and public
port refusal.

Rollback uses the previously recorded image digest and config checksum. Halt new submissions,
preserve the append-only journal, reconcile broker truth read-only, restore outside market
hours, replay, and remain in paper mode. Never infer that a pending order is unfilled.

## Gate results at handoff

| Gate | Result |
|---|---|
| B0 contract/traceability | Implemented; official FYERS decisions recorded |
| B1 remediation baseline | Verified with full, contract, chaos, research, config, secret, dependency, diff, and backup/restore checks |
| B2 paper daemon | Full scheduled session, restart, no-order, startup-failure, paper-only, and evidence-generation tests green |
| B3 adapters | Mock-only auth/data/stream/poll convergence, cumulative-fill, redaction, and health tests green |
| B4 evidence | Five-session commissioning, focused parity, current kill controls implemented |
| B5 release hardening | 158 tests passed; 90.54% overall coverage; 100% risk/execution coverage; 10 chaos and 4 research tests passed; Docker build and two smoke commands passed |
| B6 handoff | This document plus deployment plan and environment examples |

The test run emitted a known Starlette/httpx deprecation warning and non-fatal SQLite
`ResourceWarning` messages under coverage. There were no test failures. These warnings are
not commissioning evidence and should be cleaned up in a later maintenance change.

## Engineering release repository state

- Branch: `main`
- Engineering release commit: `b8c1913ab7d4ed1391188a809f64c5364e041d98`
- The documentation-record commit follows the engineering release and does not change runtime code.
- Push status: not pushed by the B0-B6 implementation task
- Real broker activity: none
- `live_trading.enabled`: `false`
- `broker.order_api_enabled`: `false`

## Known limitations and external gates

- FYERS daily 2FA is operator/account dependent. The chosen approved mechanism must be
  provisioned on the host; auth timeout halts safely.
- Official instrument/restricted-list sources and corporate-action parity must produce clean
  live artifacts during commissioning. Tests are injected/mock-only.
- Oracle deployment, five real NSE sessions, paid-host provisioning/parity, alert delivery to
  the real phone, static-IP/account acceptance, funding, and any live activation are external.
- The current Docker image exists only in the local Docker engine; registry publication and
  immutable registry-digest verification remain deployment actions.
- The user must explicitly approve the separate D7 live activation. B0-B6 does not authorize it.

## Commissioning evidence template

`ProductionPaperDaemon` generates the schema documented in
`docs/PHASE3_2_OPERATIONS.md`. Five consecutive expected NSE sessions must pass
`BurnInReview`; synthetic/local records are non-authoritative and cannot satisfy deployment
or go-live gates.
