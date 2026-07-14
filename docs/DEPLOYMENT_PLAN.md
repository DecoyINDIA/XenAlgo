# XenAlgo Deployment, Commissioning, and Go-Live Plan

**Baseline:** 2026-07-11  
**Parent plan:** [END_TO_END_COMPLETION_PLAN.md](END_TO_END_COMPLETION_PLAN.md)  
**Build prerequisite:** [PHASED_BUILD_PLAN_REMAINING.md](PHASED_BUILD_PLAN_REMAINING.md) B6 must pass.  
**Safety boundary:** Oracle is the permanent host. Commissioning and production-readiness validation remain paper/read-only. Enabling a real Fyers order path requires the separate D6 operator approval gate.

Current non-secret status and operator-owned inputs are maintained in
[DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) and
[DEPLOYMENT_OPERATOR_INPUTS.md](DEPLOYMENT_OPERATOR_INPUTS.md).

## 1. Environment Progression

| Environment | Purpose | Broker capability | State store |
|---|---|---|---|
| Local/CI | Unit, contract, integration, chaos, packaging | Mocks and `PaperBroker` only | Disposable |
| Oracle paper | Live-data software commissioning | `PaperBroker`; real order placement disabled | Dedicated paper DB |
| Oracle pre-live | Same-host mode-transition/startup proof | Paper/read-only broker observation | Dedicated parity DB |
| Oracle live | Staged real capital | Reviewed Fyers gateway after D6 approval | Dedicated live DB |

Paper and live databases must never share a path. Tokens and `.env` files remain outside the repository and backup scope.

## 2. Deployment Gates

```text
D0 Release acceptance
        |
D1 Oracle host readiness
        |
D2 Oracle paper deployment
        |
D3 Five-session commissioning
        |
D4 Oracle production-readiness validation
        |
D5 Final go-live review
        |
D6 Explicit 10% activation
        |
D7 10% -> 25% -> 50% -> 100%
        |
D8 G3 operations handoff
```

## 3. D0 - Release Acceptance

### Inputs

- B6 handoff package.
- Git commit and clean CI result.
- Docker image digest.
- Dependency and configuration checksums.
- Approved evidence-schema version.
- Rollback image and configuration.

### Acceptance

- Image is built from the approved commit.
- Both live-order flags are false.
- No secrets exist in the repository, image layers, logs, or handoff artifacts.
- Local full/coverage/contract/chaos/research gates are green.
- Operator records approval to deploy to Oracle paper only.

## 4. D1 - Oracle Host Readiness

### Host controls

- India-region Oracle VM identity recorded.
- Tailscale active; application access restricted to loopback/tailnet.
- Public application ports refused; SSH restricted according to the operations policy.
- NTP synchronized to an approved source.
- Docker and systemd installed and pinned.
- Data, journal, logs, and secret directories separated with least-privilege permissions.
- Disk, memory, service, and clock monitoring enabled.
- External heartbeat and real-phone critical alert configured.
- Off-box backup target configured without secrets/token store.
- Market-hours deployment guard enabled.

### Acceptance

- Host readiness evidence records OS, region, host ID, tailnet IP, clock offset, firewall state, storage, and service versions.
- Public console connection is refused and Tailscale health succeeds.
- Live-order flags remain false in the host configuration.
- No deployment action is performed during market hours.

## 5. D2 - Oracle Paper Deployment

### Deployment sequence

1. Confirm off-market deployment window and current kill state.
2. Back up the previous paper state and record its checksum.
3. Pull/load the approved image by immutable digest.
4. Provision non-secret configuration and secrets separately.
5. Validate file ownership and token/secret backup exclusions.
6. Run config, journal replay, calendar, data, and paper-gateway preflight checks.
7. Start the paper daemon and console under systemd.
8. Verify heartbeat, logs, health, SSE, and Tailscale access.
9. Verify the public port remains closed.
10. Record image/config/host checksums in the deployment evidence.

### Smoke tests

- Service survives restart and replays the journal.
- Kill/rearm is audit-logged and blocks paper submission within one second.
- A synthetic/mock-only host smoke event reaches the console and alert path.
- Backup completes without secret/token paths.
- Disposable restore starts with replay-consistent state.

### Acceptance

- Recovery after an induced service failure is <=60 seconds.
- No duplicate intent/order appears after restart.
- Restored state matches the backed-up journal.
- Image/config checksums equal D0.
- No real order API is called.

## 6. D3 - Five-Session Oracle Commissioning

Commissioning runs for at least five consecutive NSE trading sessions on live market data. Weekly P&L is observed but is not a pass/fail criterion.

### Daily evidence checklist

| Control | Required evidence |
|---|---|
| Authentication | Scheduled result, expiry, redacted failure state. |
| Calendar/window | Expected session and allowed execution decision. |
| Market data | Latest bar, universe/restriction freshness, sanity result. |
| Strategies | All three sleeve outcomes, including valid no-trade results. |
| Risk/governor | Every decision, scaling/rejection reason, rate counters. |
| Paper execution | Legal journal sequence and confirmed cumulative fills. |
| Reconciliation | Startup, periodic, post-execution, and EOD results. |
| Alerts | Orders, fills, rejections, breakers, health, daily summary. |
| Reliability | Heartbeat, service uptime, restart/recovery evidence. |
| Controls | Kill/rearm timing and audit trail. |
| Identity | Host, image, config, dependency, and schema checksums. |

### Acceptance

- Five consecutive expected sessions are complete and reviewed.
- Zero unresolved software or safety failure.
- Zero stale/corrupt-data trade, duplicate order, lost acknowledgement, or overnight drift.
- Authentication succeeds in all five sessions.
- All expected alerts are accounted for.
- At least one induced restart recovers within 60 seconds.
- Kill blocks new paper submissions within one second.
- A confirmed paper fill appears in the dashboard within three seconds.
- `BurnInReview` passes the signed evidence.

Any SI breach, missing session, unexplained evidence gap, or unresolved incident invalidates D3. Fixes require a new release candidate and a fresh commissioning sequence.

## 7. D4 - Oracle Production-Readiness Validation

Keep the exact commissioned image on the permanent Oracle host and validate the production
startup path in paper/read-only mode. Paper/parity and live databases must remain separate.

### Required parity checks

- Image, dependency, configuration, and evidence-schema checksums.
- Authentication and token lifecycle.
- Startup journal replay and read-only account reconciliation.
- Market data and three-sleeve results.
- Risk/governor decisions and paper execution.
- WebSocket disconnect/reconnect and REST backfill simulation.
- Periodic/post-execution reconciliation.
- Alerting, dashboard latency, heartbeat, and EOD evidence.
- Restart recovery and kill/rearm timing.
- Backup/restore on the Oracle host, including verified off-box recovery.
- Current Fyers account/network prerequisites confirmed from official sources.
- Dedicated account, allocated capital, sleeve weights, risk thresholds, and compensating
  kill controls recorded without secrets.

### Acceptance

- Every host-sensitive control passes.
- No unexplained difference from Oracle commissioning remains.
- Any approved difference is documented with its risk assessment.
- `PostMigrationValidationReview` passes focused parity evidence.
- No live order is placed and both live flags remain false.

## 8. D5 - Final Go-Live Review

All items are mandatory:

- G0, G1, G2, and Phase 3.1 are green.
- D3 commissioning and D4 production-readiness validation pass.
- Authentication proven over at least five sessions.
- Account/network startup verification is complete.
- Backup and Oracle off-box restore drill are complete.
- Kill controls and real-phone alerts are proven.
- Dedicated account is funded only with allocated capital.
- Initial stage is no more than 10%.
- Governor is capped at <=2 OPS.
- Sleeve weights, loss/drawdown thresholds, and capital amount are approved.
- Release, image, config, dependencies, host, and evidence checksums are recorded.
- Rollback and incident procedures are rehearsed.
- Activation window is outside market hours.

### Acceptance

`GoLiveChecklistReview` passes in pre-activation mode and the operator records explicit approval for D6. Passing D5 does not itself enable live trading.

## 9. D6 - Explicit 10% Activation

### Change controls

1. Confirm market is closed and no deployment lock is active.
2. Reconfirm the approved release and host checksums.
3. Back up pre-activation live state.
4. Record operator identity, timestamp, capital percentage, and approval evidence.
5. Enable only the reviewed Fyers gateway/configuration.
6. Restart through the normal startup gate.
7. Confirm auth, network/account readiness, reconciliation, data, kill state, and rate cap.
8. Do not manually force an order; allow the scheduler to create the first live intent.
9. Observe the first order lifecycle and reconcile the first confirmed fill.

### Acceptance

- Initial allocation is <=10%.
- First order passes risk, governor, journal, and legal state transitions.
- First confirmed fill matches broker truth and dashboard state.
- Alerts are delivered.
- Any ambiguity or drift immediately halts further submission.

## 10. D7 - Staged Capital Ramp

| Stage | Minimum clean evidence | Promotion authority |
|---|---|---|
| 10% | 2 calendar weeks and >=10 reviewed sessions | Explicit operator approval to 25% |
| 25% | 2 calendar weeks and >=10 reviewed sessions | Explicit operator approval to 50% |
| 50% | 2 calendar weeks and >=10 reviewed sessions | Explicit operator approval to 100% |
| 100% | 2 calendar weeks and >=10 reviewed sessions | G3 completion |

### Stage acceptance

- Zero safety incident.
- Zero duplicate order or acknowledged-order loss.
- Zero unresolved reconciliation mismatch.
- Rate remains <=2 OPS and within the daily cap.
- Scheduled authentication and sessions are complete.
- Slippage and live/backtest deviation remain within approved tolerance.
- Alerts and daily reports are complete.
- No unapproved configuration or strategy change.
- Image/config checksum continuity is maintained.
- Promotion is explicitly approved and applied outside market hours.

Any safety incident halts operation and promotion. The stage clock resumes or restarts only after documented review; it never advances automatically.

## 11. Rollback and Incident Plan

### Automatic halt conditions

- Kill switch or manual halt.
- Daily-loss/drawdown/consecutive-failure breaker.
- Stale/corrupt data or calendar uncertainty.
- Authentication failure.
- WebSocket and REST fill-observation failure beyond tolerance.
- Reconciliation mismatch.
- Journal replay/derived-state mismatch.
- Host clock drift, heartbeat loss, or invalid network/account startup check.

### Safe response

1. Halt new submissions; do not flatten automatically.
2. Preserve journal, logs, broker payloads, config, and checksums.
3. Reconcile broker truth read-only.
4. Alert the operator and classify severity.
5. Do not modify/delete `order_events`.
6. Roll back only outside market hours unless the current process cannot remain safely halted.
7. Restore the last approved image/config; replay and reconcile before resuming paper mode.
8. Require a new release candidate and relevant repeated gates before returning to live.

Rollback never assumes a pending/submitted order is unfilled. Broker truth and confirmed fills govern position state.

## 12. Backup and Recovery Plan

- Nightly SQLite backup and DuckDB/Parquet export to approved off-box storage.
- Token and secret paths excluded.
- Record backup checksums and completion alerts.
- Monthly disposable restore drill after go-live.
- RPO <=24 hours for analytical/state backups; acknowledged orders remain recoverable from broker reconciliation and journal durability.
- RTO <=1 hour, while remaining safely halted until reconciliation is clean.

Restore acceptance: schema loads, journal integrity passes, replay equals derived state, configuration identity is known, and the service starts in disabled/paper mode before any live re-authorization.

## 13. Deployment Completion Matrix

| Gate | Status on 2026-07-14 | Completion evidence |
|---|---|---|
| D0 Release acceptance | Superseding source accepted; image pending | Commit `b0d7d1c` is pushed in draft PR #1 and both CI runs pass; exact-commit Oracle image and rollback identities remain pending after the market-hours lock. |
| D1 Oracle readiness | Complete | Tailscale-only access, monitoring, heartbeat/phone alert, off-box backup, restore, NTP, permissions, and market-hours guard are proven. |
| D2 Oracle paper deploy | Runtime controls complete; identity pending | Authentication, startup and scheduled preflight, read-only completed-bar data, synthetic event delivery, restart/kill/restore, and zero real order calls are proven; exact D0/D2 image identity must be refreshed from the commit-built image. |
| D3 Five-session commissioning | External | Five consecutive reviewed NSE sessions. |
| D4 Oracle production readiness | External | Focused same-host paper/read-only evidence. |
| D5 Final review | External | Complete go-live checklist. |
| D6 10% activation | External | Separate explicit operator approval. |
| D7 Capital ramp | External | At least two clean weeks per stage. |
| D8 G3 handoff | Pending | 100% stage completed cleanly. |

### Executable evidence map

The gate policy is executable without granting deployment or broker authority:

- `xenalgo.deployment`: D0 release, D1 host, D2 paper deployment, SQLite
  backup/restore integrity, paper-config validation, and D8 handoff completeness.
- `xenalgo.phase32`: D3 five-session commissioning and permanent-host readiness.
- `xenalgo.phase33`: D4 focused same-host production-readiness validation.
- `xenalgo.phase34`: D5 pre-activation review and D6 activation evidence.
- `xenalgo.phase35`: D7 staged capital ramp.
- `deploy/evidence/`: fail-closed, non-secret templates and storage rules.

An evaluator pass means the supplied evidence satisfies policy; it never performs a
deployment, changes configuration, calls Fyers, or substitutes synthetic records for
external evidence.

## 14. D8 - G3 Operations Handoff

G3 completes only after the 100% stage finishes its clean evidence window.

The final operations package contains:

- Approved release and current checksums.
- Full commissioning, parity, activation, and ramp evidence.
- Current positions/reconciliation state and capital allocation.
- Backup/restore and incident records.
- Risk limits, sleeve weights, and approval history.
- Monitoring and alert ownership.
- Next restore-drill and review dates.
- Known risks and Phase 4/G4 operating boundary.

G3 does not remove any guardrail or approval requirement. Subsequent live deployments repeat D0, D4-equivalent production-readiness checks, and the appropriate operator change approval.
