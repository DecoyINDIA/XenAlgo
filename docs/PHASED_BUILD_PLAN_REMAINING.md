# XenAlgo Phased Remaining-Build Plan

**Baseline:** 2026-07-11  
**Parent plan:** [END_TO_END_COMPLETION_PLAN.md](END_TO_END_COMPLETION_PLAN.md)  
**Scope:** Repository engineering required before Oracle commissioning.  
**Safety boundary:** All development and automated verification use mocks or `PaperBroker`. This plan does not authorize a real Fyers order call or changing either live-order flag to `true`.

## 1. Build Definition of Done

The remaining build is complete only when a production paper daemon can run the full scheduled XenAlgo session on live Fyers market data while all order placement remains simulated.

Every phase must preserve:

- Mandatory `RiskEngine.check()` on every submission path.
- Governor enforcement at no more than 2 orders per second.
- Append-only `order_events`.
- Position mutation only from confirmed cumulative fills.
- Idempotent correlation/tag handling and no blind POST retry.
- Paper/live separation through physical state stores and gateway injection.
- No changes to the three validated strategies unless separately requested.

## 2. Phase Dependency Graph

```text
B0 Contract and decision freeze
        |
B1 Remediation baseline closure
        |
        +------------------+
        |                  |
B2 Paper daemon core   B3 Fyers adapters
        |                  |
        +--------+---------+
                 |
B4 Evidence gates and observability
                 |
B5 Release-candidate hardening
                 |
B6 Build handoff to deployment
```

No phase advances with a safety-invariant regression. B2 and B3 may proceed in parallel only after B1 is committed and their shared interfaces are frozen.

## 3. B0 - Fyers Contract and Decision Freeze

### Objective

Make one broker/runtime design authoritative before adding more code.

### Build tasks

| ID | Task | Primary artifacts |
|---|---|---|
| B0.1 | Verify current Fyers OAuth, order, fill, symbol, rate-limit, data, and network contracts from official sources. | Source-backed decision notes in governing docs. |
| B0.2 | Remove active Dhan/postback/broker-kill requirements and stale terminology. | `PLAN.md`, PRD, TRD, build/test/success docs, runbooks. |
| B0.3 | Freeze broker-neutral interfaces for auth, market data, order gateway, fill stream, and orderbook polling. | `xenalgo/broker/`, TRD interface definitions. |
| B0.4 | Confirm Python/runtime and SDK containment policy. | Dependency files, CI, Dockerfile, TRD. |
| B0.5 | Record operator-owned decisions that affect implementation. | Decision table in the parent plan/handoff. |
| B0.6 | Repair FR/component/SI/test traceability. | PRD/TRD/test headers and matrix. |

### Exit gate B0

- Fyers is the only active execution contract.
- No acceptance criterion depends on a nonexistent broker capability.
- All unresolved operator decisions are explicitly marked and do not silently default into live behavior.
- SI-1 through SI-12 remain mapped to tests.
- Docs and code use consistent names for symbols, order IDs, cumulative fill quantity, and terminal states.

## 4. B1 - Commissioning Remediation Baseline Closure

### Objective

Turn the current uncommitted A-G remediation into a clean, reviewed baseline.

### Build tasks

| ID | Task | Required proof |
|---|---|---|
| B1.1 | Review persistent failure breaker, dynamic risk context, and single-engine lifecycle. | Focused execution/risk tests. |
| B1.2 | Verify governor token-bucket and daily-cap wiring before broker access. | Burst test and broker-call count. |
| B1.3 | Verify legal `INTENT -> SUBMITTED -> PENDING/REJECTED` routing. | State transition and journal sequence tests. |
| B1.4 | Verify cumulative partial-fill accounting in runtime, replay, and console. | 4 -> 10 equals 10; duplicate equals no-op. |
| B1.5 | Verify Fyers bind/auth/gateway/data scaffolding and secret isolation. | Unit/contract/security tests. |
| B1.6 | Verify legacy `Brain` live path cannot place orders. | Import/instantiation guard test. |
| B1.7 | Run all release checks and commit the baseline. | Clean CI-quality evidence. |

### Exit gate B1

- Full suite green from a stable repository-local temp directory.
- Overall coverage at least 90%; risk and execution coverage 100%.
- Contract and chaos suites green with zero real broker calls.
- Research tests green.
- Config validation, secret scan, `git diff --check`, and CI green.
- Remediation committed before B2/B3 implementation begins.

## 5. B2 - Production Paper Daemon Core

### Objective

Create the supervised unattended scheduler/orchestrator used for Oracle commissioning.

### Build tasks

| ID | Task | Key behavior |
|---|---|---|
| B2.1 | Add a production paper entry point and dependency container. | Hard-wire `PaperBroker`; reject live gateway injection. |
| B2.2 | Implement lifecycle ownership. | One journal, engine, broker, fill listener, reconciler, scheduler, and alert bus per process. |
| B2.3 | Implement the startup gate. | Auth, calendar, config checksum, journal replay, data readiness, kill/breaker state, reconciliation. |
| B2.4 | Implement scheduled job orchestration. | Token, data, startup, reconciliation, execution, EOD, backup, heartbeat jobs. |
| B2.5 | Implement three-sleeve session execution. | Current completed bars, sleeve isolation, netting, SELL-before-BUY, risk context refresh. |
| B2.6 | Implement paper fills from current Fyers prices. | Same execution path; no real order call. |
| B2.7 | Implement EOD evidence generation. | Session result, alerts, reconciliation, checksums, incidents, summaries. |
| B2.8 | Implement graceful shutdown and restart recovery. | No lost acknowledgement or duplicated intent. |

### Required tests

- Clock-controlled full scheduled session.
- Non-rebalance and holiday no-order sessions.
- Startup failure for every failed prerequisite.
- Three-sleeve isolation and netting.
- Kill/breaker checks before every submission.
- Restart at each order state.
- Alert failure is logged but never corrupts state.
- Static proof that production paper composition cannot access a live gateway.

### Exit gate B2

- A complete scheduled paper session runs unattended in integration tests.
- The production paper entry point cannot place a real order even with credentials present.
- Every event is journaled and reflected in the read model.
- Restart/replay is deterministic and idempotent.
- All expected session evidence is generated in the Phase 3.2 input format.

## 6. B3 - Fyers Operational Adapters

### Objective

Finish the live-data and broker-observation boundaries required by the paper daemon and later live gateway commissioning.

### B3A - Authentication

| ID | Task | Proof |
|---|---|---|
| B3.1 | Implement the approved OAuth provider behind `TokenManager`. | Mocked success/failure/expiry tests. |
| B3.2 | Supervise renewal/login workflow and timeouts. | No infinite wait; session halts on failure. |
| B3.3 | Isolate token state from git and backups. | Permissions and manifest tests. |
| B3.4 | Redact auth material from errors and logs. | Structured-log tests. |

### B3B - Market data

| ID | Task | Proof |
|---|---|---|
| B3.5 | Complete symbol/instrument resolution. | Unique NSE cash mappings. |
| B3.6 | Complete daily-history ingestion and single-writer persistence. | Deterministic dataset tests. |
| B3.7 | Implement universe/corporate-action parity reporting. | Reconciliation artifact with explained differences. |
| B3.8 | Apply freshness, sanity, duplicate, gap, and calendar checks. | Fail-closed data tests. |
| B3.9 | Refresh restricted symbols/circuit/manual blacklist inputs. | Freshness and missing-source blockers. |

### B3C - Fill observation

| ID | Task | Proof |
|---|---|---|
| B3.10 | Implement supervised Order WebSocket adapter. | Connect, disconnect, timeout, reconnect tests. |
| B3.11 | Normalize order/trade payloads. | Partial, complete, rejected, cancelled, malformed cases. |
| B3.12 | Implement REST orderbook polling fallback. | Missed WebSocket fill recovery. |
| B3.13 | Apply both channels through one idempotent fill listener. | Duplicate and out-of-order tests. |
| B3.14 | Expose channel health to startup/monitoring/evidence. | Health state and alert tests. |

### Exit gate B3

- No secret leaks and auth failures halt safely.
- Data parity has no unexplained material difference.
- Stale/corrupt data cannot reach sizing or order construction.
- WebSocket and polling updates converge to one correct position state.
- A stream outage is recovered and backfilled without duplicate fill application.
- All automated tests remain mock-only.

## 7. B4 - Evidence Gates and Observability

### Objective

Make repository evaluators match the approved commissioning and deployment process.

### Build tasks

| ID | Task | Acceptance |
|---|---|---|
| B4.1 | Update Phase 3.2 policy to five consecutive NSE sessions. | Missing/nonconsecutive/unresolved sessions fail. |
| B4.2 | Replace Phase 3.3 duration with focused deployment parity. | Required controls and checksum identity drive pass/fail. |
| B4.3 | Align Phase 3.4/3.5 kill evidence with available Fyers and compensating controls. | No false requirement; no weakened kill gate. |
| B4.4 | Update CSV schemas, loaders, examples, and runbooks. | Round-trip tests and fail-closed parsing. |
| B4.5 | Add daemon/session/adapter health to console and alerts. | Paper fill <=3 seconds; control path <=1 second. |
| B4.6 | Make evidence tamper-evident. | Checksums, timestamps, host/image/config identity. |

### Exit gate B4

- Phase 3.2-3.5 evaluators encode the current decisions exactly.
- Local synthetic evidence is visibly non-authoritative for external gates.
- Required daemon and channel health is observable without exposing secrets.
- Evidence produced by B2 is directly consumable by the updated evaluators.

## 8. B5 - Release-Candidate Hardening

### Required gate bundle

1. Full pytest suite.
2. Overall coverage >=90%.
3. Risk and execution coverage =100%.
4. Contract suite with injected/mocked Fyers clients.
5. Full chaos suite.
6. At least 1,000 restart/idempotency iterations.
7. Research suite.
8. Config validation for research and live profiles.
9. Docker image build and smoke test.
10. Dependency and secret scans.
11. Journal replay equals derived state.
12. Disposable backup and restore rehearsal.
13. Documentation traceability audit.

### Automatic blockers

- Any SI failure.
- Any test touching the real Fyers API.
- Any `RiskEngine` or governor bypass.
- Any position mutation from a non-fill state.
- Any update/delete path for `order_events`.
- Any unresolved reconciliation mismatch.
- Any secret or token in source, logs, evidence, image layers, or backups.
- Any unreviewed change to `Strategies/` or validated research behavior.

### Exit gate B5

Create an immutable release candidate identified by Git commit, Docker image digest, dependency lock checksum, config checksum, and evidence-schema version.

## 9. B6 - Deployment Handoff

### Required handoff package

- Release commit and image digest.
- Exact startup and health commands.
- Non-secret environment-variable manifest.
- Secret provisioning checklist without secret values.
- Database and backup paths.
- Rollback image/config/checksum.
- Known limitations and accepted risks.
- B0-B5 gate results.
- Phase 3.2 commissioning evidence template.

### Exit gate B6

The deployment operator can deploy, verify, roll back, and collect commissioning evidence without making an undocumented code or configuration decision. Deployment then follows [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md).

## 10. Build Completion Matrix

| Phase | Current status | Completion proof |
|---|---|---|
| B0 Contract freeze | Complete | `FYERS_CONTRACT.md`, frozen protocols, traceability matrix. |
| B1 Remediation baseline | Complete | CI-quality remediation retained and reverified. |
| B2 Production paper daemon | Complete | Full scheduled paper session and restart/no-order/startup tests. |
| B3 Fyers operational adapters | Complete | Mock-only auth/data/fill convergence and health proof. |
| B4 Evidence and observability | Complete | Current evaluators, schemas, health, and tamper-evident evidence. |
| B5 Release candidate | Complete locally | Gate bundle and image smoke pass; final identifiers recorded at handoff. |
| B6 Deployment handoff | Complete | `HANDOFF.md`, deployment plan, environment manifests, rollback/evidence package. |

## 11. Immediate Build Order

1. Complete B0.
2. Complete and commit B1.
3. Freeze shared B2/B3 interfaces.
4. Build B2 and B3 with test-first safety coverage.
5. Complete B4.
6. Pass B5 without exceptions.
7. Produce B6 and stop before any live activation.
