# XenAlgo End-to-End Completion Plan

**Approved planning baseline:** 2026-07-11  
**Scope:** Contract freeze through paper commissioning, paid-host migration, live capital ramp, and operational learning.  
**Safety boundary:** This plan does not authorize a real Fyers order call or enable live trading. Live activation remains a separate, explicit operator decision.

Execution documents:

- [PHASED_BUILD_PLAN_REMAINING.md](PHASED_BUILD_PLAN_REMAINING.md) converts W0-W5 into engineering phases B0-B6 with task-level exit gates.
- [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) converts W6-W10 into deployment gates D0-D9 covering Oracle commissioning, paid-host parity, activation, rollback, recovery, and the capital ramp.

## 1. Definition of Complete

XenAlgo is complete only when all of the following are true:

- Paper and live modes use the same guarded pipeline; only the broker gateway differs.
- Every order passes through the `RiskEngine`, governor, append-only journal, and legal order state machine.
- Positions change only from confirmed cumulative fill events.
- The Oracle paper host completes five consecutive reviewed NSE trading sessions.
- The paid live host passes focused deployment-parity checks.
- The operator explicitly approves the initial 10% live-capital stage.
- The 10% -> 25% -> 50% -> 100% ramp completes with at least two clean weeks and 10 reviewed trading sessions at each stage.
- Learning proposals remain proposal-only until an authenticated human approval is audit-logged.

Safety invariants SI-1 through SI-12 in `SUCCESS_CRITERIA.md` are continuous release blockers. Feature completion never overrides an invariant failure.

## 2. Dependency Chain

```text
Contract freeze
      |
Close remediation baseline
      |
Production paper daemon
      |
Fyers auth, data, and fill integration
      |
Local release-candidate gates
      |
Oracle paper deployment
      |
Five-session commissioning
      |
Paid live-host migration
      |
Deployment-parity checks
      |
Explicit 10% go-live approval
      |
10% -> 25% -> 50% -> 100%
      |
G3 production completion
      |
G4 operational learning
```

Calendar evidence cannot be replaced with local tests. After implementation is ready, G3 still requires five consecutive NSE commissioning sessions plus at least eight clean live weeks across the four capital stages.

## 3. Workstreams and Acceptance Gates

### W0 - Authoritative Fyers contract freeze

Synchronize `PLAN.md`, the PRD, TRD, build plan, success criteria, test plan, operations runbooks, config examples, and evidence schemas around one Fyers design.

Required work:

- Remove active Dhan gateway, postback, error-code, static-IP, account, and broker-kill assumptions unless retained explicitly as historical context.
- Define fills as Fyers Order WebSocket plus REST orderbook polling, with cumulative fill accounting and no public postback route.
- Verify current Fyers OAuth, rate limits, order statuses, cumulative-fill fields, symbols, network requirements, and available account controls from official sources before live commissioning.
- Resolve Python runtime and SDK support statements.
- Record operator decisions for live host, account/capital, sleeve weights, breaker thresholds, and compensating kill controls.
- Restore the PRD goal -> FR -> TRD component -> build task -> success criterion/SI -> test traceability chain.

Acceptance:

- No active document identifies Dhan as the execution broker.
- No mandatory acceptance criterion requires a Fyers capability that does not exist.
- Every FR has an implementation and test/evidence route.
- No SI-1 through SI-12 control is weakened.
- Material operator decisions are recorded before runtime implementation depends on them.

### W1 - Close the commissioning remediation baseline

Review and finish the current A-G remediation work before adding the production daemon.

Acceptance:

- Full repository suite passes from a clean repository-local temporary directory.
- Overall coverage is at least 90%; `xenalgo/risk.py` and `xenalgo/execution/*` are 100% covered by the safety gate.
- Contract and chaos suites are green without real broker calls.
- The optional `_source/Lab` research suite remains green.
- Legacy `Brain` live-order code cannot place an order.
- `git diff --check`, secret scanning, config validation, and CI pass.
- The baseline is committed as a small, reviewable change set before daemon work begins.

Planning-time evidence: the ordinary suite passed 148 tests. Overall coverage measured 91.76%, with risk and execution at 100%, but that coverage invocation ended with a Windows temporary-directory setup error and is not yet an acceptance-quality clean run.

### W2 - Production paper daemon

Build the unattended, data-only service that operates the existing paper pipeline on the Oracle host.

Required daily rhythm:

| Time (IST) | Required action |
|---|---|
| 02:00 | Back up non-secret state and export market data according to the operations policy. |
| 08:15 | Complete Fyers authentication/token validation; halt and alert on failure. |
| 08:30 | Sync history/instruments, refresh restrictions, validate universe and data. |
| 09:00 | Run journal replay, startup gate, configuration check, and reconciliation. |
| Market hours | Monitor health and reconcile every 15 minutes. |
| 15:00-15:20 | On configured rebalance days, run all three sleeves and paper execution. |
| 15:45 | Reconcile, persist daily evidence, send summary, and close the session. |

Hard restrictions:

- Use `PaperBroker` only.
- Keep `live_trading.enabled=false` and `broker.order_api_enabled=false`.
- Do not call `FyersGateway.place_order()`.
- Do not mutate positions from acknowledgements, pending states, or assumed fills.
- Do not create a second DuckDB writer.
- Do not blindly retry an ambiguous order POST.

Acceptance:

- A complete scheduled paper session runs without operator action.
- Startup fails closed on invalid auth, stale/corrupt data, calendar mismatch, journal mismatch, dirty reconciliation, invalid config, or an active halt/kill state.
- All three sleeves flow through the same risk, governor, journal, and execution path.
- No production-paper dependency can resolve to a live gateway.
- Restart at every order state loses no acknowledged state and creates no duplicate order.
- Alerts and daily evidence cover every expected action and failure.

### W3 - Fyers operational integration

#### Authentication

- Supervise the approved OAuth flow.
- Store ephemeral tokens outside the repository and backup scope with restrictive permissions.
- Block the session and issue a critical alert when authentication cannot complete safely.

Acceptance: five consecutive commissioning authentications succeed; missing/expired credentials prevent submission; secret values never appear in code, logs, journal payloads, CI, or artifacts.

#### Market data

- Ingest Fyers daily history through the single-writer data path.
- Resolve `NSE:<SYMBOL>-EQ` consistently.
- Reconcile corporate-action treatment and universe membership against the validated historical dataset.
- Validate dates, OHLC relationships, volume, gaps, duplicates, and freshness.

Acceptance: every commissioned symbol resolves uniquely; no unexplained parity discrepancy remains; the expected completed trading date is present; stale or corrupt data blocks affected execution; strategy code remains unchanged.

#### Fill channels

- Supervise the Fyers Order WebSocket and reconnect/backfill after failure.
- Convert cumulative filled quantity to the incremental local delta.
- Poll the REST orderbook as the redundant recovery channel.
- Deduplicate updates arriving through both channels.

Acceptance: cumulative fills 4 then 10 produce position 10, duplicates are no-ops, missed WebSocket fills are recovered through polling, and any unresolved divergence trips reconciliation and halts.

### W4 - Evidence evaluator alignment

Required changes:

- Change Phase 3.2 from the legacy 28-day/18-session defaults to five consecutive reviewed NSE sessions.
- Change Phase 3.3 from a fixed calendar week to focused deployment parity.
- Replace Dhan-specific and unavailable broker-side kill evidence with the approved Fyers controls and compensating evidence.
- Update Phase 3.2-3.5 CSV schemas, examples, runbooks, tests, and failure messages.

Acceptance:

- Phase 3.2 passes exactly the governing five-session requirement and fails on a missing or unresolved session.
- Phase 3.3 measures migrated-host controls rather than elapsed time.
- Phase 3.4 cannot pass without every preceding gate and explicit operator approval.
- Phase 3.5 enforces stage order, minimum duration, clean reconciliation, approval, checksum continuity, and non-overlap.
- Synthetic local evidence cannot mark an external gate complete.

### W5 - Local release candidate

Required gates:

- Full pytest suite.
- Overall coverage >=90% and safety-critical coverage =100%.
- Mock-only Fyers contract tests.
- Full chaos and 1,000-restart idempotency proofs.
- Research suite, configuration validation, Docker build, dependency review, secret scan, journal replay equality, and disposable backup/restore rehearsal.

Automatic blockers include any SI failure, real broker call from tests, `RiskEngine` bypass, non-fill position mutation, journal update/delete path, unresolved reconciliation defect, secret exposure, or coverage below target.

### W6 - Oracle paper deployment

Deploy the exact release-candidate image with supervised services, Tailscale-only console access, NTP, heartbeat, log/disk monitoring, off-box backups, and restart recovery.

Acceptance:

- Live/order flags remain false.
- Public application ports are refused and Tailscale access is healthy.
- An induced service failure recovers within 60 seconds without journal divergence.
- A disposable restore becomes operational.
- Heartbeat loss reaches the real operator phone.
- Image and configuration checksums match the approved release candidate.

### W7 - Five-session software commissioning

For five consecutive NSE sessions, record scheduled startup, authentication, calendar decision, data freshness, all three sleeve results, risk decisions, paper orders/fills, reconciliation, alerts, journal state, dashboard reflection, heartbeat, restart recovery, kill behavior, and EOD summary.

Acceptance:

- Every expected session is accounted for.
- Zero unresolved software or safety incident.
- Zero stale/corrupt-data trade, duplicate order, lost acknowledgement, or overnight reconciliation mismatch.
- Authentication succeeds for all five sessions.
- Required alerts are complete.
- Induced restart recovery is <=60 seconds.
- Kill switch blocks submission within one second.
- Dashboard reflects a confirmed paper fill within three seconds.
- Profit is recorded for observation but is not a commissioning pass/fail criterion.

An SI breach invalidates the gate; commissioning restarts after remediation and a new release candidate.

### W8 - Paid live-host preparation and parity

The operator selects AWS Mumbai or DigitalOcean Bangalore, provisions the paid host, confirms current Fyers network requirements, deploys the commissioned image, configures supervision/security/backups/alerts, and keeps live order placement disabled.

Acceptance:

- Host, image, configuration, and dependency checksums match the commissioned release.
- Required broker/network identity is accepted.
- Read-only startup reconciliation works against the intended account.
- Backup/restore, real-phone alerts, Tailscale access, and public-port refusal are proven.
- Focused paper-mode authentication, data, sleeves, risk, fills, reconciliation, restart, kill, and EOD checks all pass on the new host.
- No live order API is called during the parity gate.

### W9 - Explicit 10% activation

This is a separate operator-authorized, off-market action. It is not implied by completing any earlier workstream.

Required evidence: G0-G2, Phase 3.1, Oracle commissioning, paid-host parity, at least five authentication sessions, backup/restore, real-phone alerts, approved kill controls, dedicated funded account, final risk/sleeve decisions, <=2 OPS governor, no more than 10% initial allocation, recorded checksums, and explicit operator approval.

Acceptance: activation occurs off-market; only the reviewed gateway is enabled; the startup gate independently rechecks prerequisites; the first live order is produced by the scheduler rather than manually forced; every fill reconciles; any discrepancy halts further submission.

### W10 - Staged capital ramp and G3

| Stage | Minimum observation | Promotion gate |
|---|---|---|
| 10% | 2 clean weeks and >=10 reviewed sessions | Explicit operator approval |
| 25% | 2 clean weeks and >=10 reviewed sessions | Explicit operator approval |
| 50% | 2 clean weeks and >=10 reviewed sessions | Explicit operator approval |
| 100% | 2 clean weeks and >=10 reviewed sessions | G3 completion |

Every stage requires zero safety incidents, zero unresolved reconciliation drift, zero duplicate orders, zero acknowledged-order loss, <=2 OPS, clean authentication/scheduling, approved deviation and slippage, complete alerts/reports, checksum continuity, no unapproved config change, and an off-market operator-approved promotion.

A safety incident halts the system for review; it does not automatically continue or preserve the stage clock.

### W11 - Operational learning and G4

Select an approved provider or offline mode, generate structured proposals from real journal evidence, validate provenance/schema, and approve or reject through the authenticated console.

Acceptance: at least one real proposal is reviewed; every decision is audit-logged; rejected proposals change nothing; approved changes are versioned and applied outside market hours; no live risk limit changes without explicit approval.

## 4. Completion Matrix

Legend: **Complete** = repository/host evidence exists; **Partial** = implementation exists but its authoritative gate is incomplete; **Pending** = build work remains; **External** = operator, host, broker, or calendar evidence is required.

| Area | Status on 2026-07-11 | Evidence required to close |
|---|---|---|
| Foundation, journal, replay, RiskEngine | Complete | Preserve all current gates. |
| Governor and legal state transitions | Partial | Commit remediation; clean CI and coverage. |
| Cumulative partial-fill accounting | Partial | Commit remediation; clean integration/contract proof. |
| Legacy Dhan live route removal | Partial | Commit deletion/quarantine proof. |
| PaperBroker contract | Complete | Preserve mock-only contract suite. |
| Fyers gateway abstraction | Partial | Operational runtime and parity evidence. |
| Fyers OAuth runtime | Partial | Five host sessions without secret leakage. |
| Fyers Order WebSocket supervisor | Pending | Reconnect and fill recovery evidence. |
| REST orderbook fill fallback | Pending | Missed-fill recovery and dedup evidence. |
| Fyers historical data parity | Partial | Real dataset reconciliation report. |
| Production paper daemon | Pending | Full scheduled host-side paper session. |
| Three-sleeve unattended runtime | Pending | Five-session commissioning evidence. |
| Restricted-list production ingestion | Pending | Fresh source and fail-closed proof. |
| Startup reconciliation against Fyers | Pending | Read-only account/host proof. |
| Console/Tailscale/public-port controls | Complete | Preserve deployment evidence. |
| Host-side fill push <=3 seconds | Pending | Production paper daemon measurement. |
| Dashboard kill <=1 second | Complete | Current recorded result: 333 ms. |
| Telegram kill path | Partial | Host commissioning proof. |
| Phase 3.1 chaos suite | Complete | Re-run on every release candidate. |
| Overall coverage >=90% | Partial | Clean coverage invocation; current measurement 91.76%. |
| Risk/execution coverage =100% | Complete | Preserve CI enforcement. |
| Phase 3.2 evaluator | Partial | Replace legacy 28/18 defaults. |
| Phase 3.3 evaluator | Partial | Replace legacy fixed-week gate. |
| Phase 3.4/3.5 broker control evidence | Partial | Align to actual Fyers controls. |
| Oracle paper deployment | Pending | Daemon service and scheduled evidence. |
| Five-session commissioning | External | Five consecutive NSE sessions. |
| Paid live host and network readiness | External | Operator/provider/broker actions. |
| Backup/restore and real-phone proof | External | Live-host operational drills. |
| Dedicated funded account | External | Operator/account action. |
| 10%, 25%, 50%, 100% stages | External | Explicit approvals and calendar evidence. |
| Phase 4 scaffolding | Complete | Preserve proposal-only controls. |
| Operational G4 | External | Real proposal and human review. |

## 5. Phase Gate Summary

| Gate | Definition | Status on 2026-07-11 |
|---|---|---|
| G0 | Foundation, pinned build, clean CI | Partial while remediation is uncommitted. |
| G1 | Autonomous guarded paper pipeline | Partial; production scheduled daemon is missing. |
| G2 | Secure observation and kill controls | Partial; host-side fill timing awaits the daemon. |
| G3 | Commissioned, migrated, approved, and live at 100% after the ramp | Pending. |
| G4 | Real reviewed proposals with mandatory human approval | Partial; scaffolding exists, operational proof does not. |

## 6. Immediate Execution Order

After operator approval to resume implementation:

1. Complete W0 and make Fyers the only authoritative broker contract.
2. Complete W1 and establish a clean committed remediation baseline.
3. Implement W2 production paper daemon without adding any live-order path.
4. Complete W3 and W4, then pass W5 locally.
5. Deploy W6 and begin W7 commissioning only after the daemon is proven on-host.
