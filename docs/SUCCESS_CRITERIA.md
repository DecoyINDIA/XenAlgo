# XenAlgo — Success Criteria & Acceptance Gates

**Version:** 1.0 · **Date:** 2026-07-04

Every criterion is **measurable and testable**. A phase gate passes only when all of its criteria are met. Criteria trace to PRD goals (G1–G6) and requirements.

---

## 1. Phase Exit Gates (must all pass)

**Current evidence snapshot (2026-07-11):** G0, G1, and the repository-local Phase 3.1
failure-injection suite are locally green. The Oracle/Tailscale console host is deployed;
private access, public port refusal and the authenticated 333 ms kill/rearm route are proven.
Snapshot/SSE fill visibility remains locally covered until the production paper daemon can
produce a scheduled host-side fill. Phase 3.2, Phase 3.3, Phase 3.4, and Phase 3.5 have local evidence evaluators,
but the real gates still require operator-supplied host, calendar-time, live-activation,
and staged-ramp proof. Full
G3 go-live remains blocked by
external/operator gates: Oracle-host proof, one-week software commissioning, live-host migration,
Dhan static-IP registration, backup/restore drills, live-host deployment-parity validation,
live kill-switch proof, funded account setup, operator-approved 10% activation, and staged
capital ramp.

### G0 — Foundation
- [ ] `pytest` full suite green (existing 4 + new).
- [ ] Project imports cleanly; both config profiles load and validate.
- [ ] All dependencies pinned; lockfile committed; CI green.

### G1 — Execution Core (paper)
- [ ] A full simulated trading day completes unattended (token → data → signal → risk → order → fill → reconcile → journal → alert).
- [ ] **100%** of RiskEngine checks and order-state transitions covered by passing tests.
- [ ] **Zero double-orders** across 1,000 simulated restart-mid-order iterations (idempotency proof).
- [ ] Positions **never** mutate on a non-fill event (property test).
- [ ] Journal survives kill -9 mid-write; replay == derived state on restart.
- [ ] Governor never exceeds 2 orders/sec under a 100-order burst.
- [ ] Reconciler detects an injected 1-share drift and halts.

### G2 — Console
- [ ] Dashboard reflects a paper fill within **3 s** (measured).
- [ ] Kill switch via each of 3 paths halts new-order submission within **1 s** (measured).
- [ ] No public inbound ports except the HMAC-validated Postback webhook (port scan proof).
- [ ] Reachable only over Tailscale (verified from off-tailnet = refused).

Local status: snapshot/SSE fill visibility and dashboard/Telegram kill-switch behavior are
covered in `tests/integration/test_phase2_console.py`. The deployed Tailscale route, public
port refusal and authenticated dashboard kill/rearm path are proven; a scheduled host-side
fill timing remains pending on the production paper daemon.

### G3 — Go-Live
- [ ] Full failure-injection suite (Phase 3.1) **100%** green.
- [ ] One paper commissioning week covering at least five consecutive NSE trading sessions on live market data completed.
- [ ] Every expected session completes its schedule, data-freshness checks, three-sleeve signal generation, risk decisions, paper execution, confirmed-fill accounting, reconciliation, journal writes, alerts and daily summary without an unresolved software or safety failure.
- [ ] Weekly profit is recorded for observation but is not a commissioning pass/fail criterion; strategy validation rests on the existing five-year backtest evidence.
- [ ] Token auto-refresh succeeded on ≥5 consecutive live sessions.
- [ ] Static IP registered & startup-verified; DH-905/invalid-IP path proven.
- [ ] Backup + **restore drill** completed successfully.
- [ ] Kill switch verified against the live broker (Trader's-Control path).
- [ ] Staged ramp complete: 10→25→50→100%, each ≥2 clean weeks.

Local status: `tests/chaos/` covers the Phase 3.1 failure list locally. The remaining G3
items require real host, broker, account, phone-alert, calendar-time, and operator evidence;
they must not be marked complete from local tests alone.

Phase 3.2 evidence support is covered locally by `tests/unit/test_phase32_readiness.py`:
commissioning records are intended to check five consecutive reviewed trading sessions, complete sleeve reviews, token refresh, safety incidents and unresolved software outliers. The current `BurnInReview` implementation still carries the legacy 28-calendar-day/18-trading-day defaults and must be updated and re-tested before it is used as the authoritative commissioning evaluator. Until then, the signed daily evidence plus this acceptance checklist are the governing decision record. The existing evaluator also checks deviation ratio,
token refresh success, safety incidents, and unresolved outliers; live-host evidence is
checked for India-region host selection, static-IP lead time, Docker/systemd/backups/restore,
heartbeat, Oracle warm-staging retention, and live-order toggles remaining disabled. Passing
these local checks is necessary evidence hygiene, not a substitute for the external gate.

Phase 3.3 evidence is intended to cover focused deployment parity on the paid host: image and
config checksum identity, host-id consistency, static-IP startup verification, token refresh,
three-sleeve paper execution, clean reconciliation, alerts, restart recovery, kill-switch
behaviour, no safety incidents, and live-order toggles remaining disabled. The current
`PostMigrationValidationReview` still encodes the legacy one-week defaults and must be
updated before it becomes authoritative for the revised gate.

Phase 3.4 evidence support is covered locally by `tests/unit/test_phase34_go_live.py`:
the go-live checklist is checked for all prior phase gates, live-host identity, config
checksum, static-IP startup verification, at least five token-refresh sessions,
backup/restore drill, broker-side kill switch proof, real-phone alerts, dedicated funded
account, explicit operator approval, initial capital at no more than 10%, the 2 OPS
governor cap, and off-market activation timing. Passing this local check is necessary
evidence hygiene, not a substitute for external proof or the operator's live enablement
decision.

Phase 3.5 evidence support is covered locally by `tests/unit/test_phase35_capital_ramp.py`:
the staged-ramp evidence is checked for Phase 3.4 prerequisite proof, the exact
10% -> 25% -> 50% -> 100% order, at least two calendar weeks and 10 reviewed trading days
per stage, complete sleeve reviews, live-vs-backtest deviation tolerance, zero safety
incidents, clean reconciliation, broker-side kill switch evidence, explicit operator
approval per stage, config checksums, the 2 OPS governor cap, off-market stage changes, and
non-overlapping stage order. Passing this local check is necessary evidence hygiene, not a
substitute for the live staged ramp itself.

### G4 — Learning Layer
- [ ] Produces structured post-trade insights + parameter proposals.
- [ ] **No** live risk-limit change occurs without explicit operator approval (enforced + audit-logged).

---

## 2. Safety Invariants (must hold at all times, continuously tested)

| # | Invariant | Verification |
|---|---|---|
| SI-1 | No order exceeds max notional. | Pre-trade check + property test. |
| SI-2 | No single position exceeds 10% of portfolio. | Pre-trade check + reconciliation audit. |
| SI-3 | Positions change only from confirmed fills. | Property test over random event streams. |
| SI-4 | No duplicate order for the same correlationId. | Idempotency test + journal uniqueness. |
| SI-5 | Outgoing order rate ≤2/sec, ≤ daily cap. | Governor test under burst. |
| SI-6 | No trading on stale/corrupt data. | Freshness/sanity gate tests. |
| SI-7 | Drawdown-halt requires manual re-arm. | Breaker state-machine test. |
| SI-8 | Local state reconciles to broker truth or halts. | Reconciler drift tests. |
| SI-9 | Restart never loses an acknowledged order. | kill -9 durability test. |
| SI-10 | Kill switch halts submission within 1 s via any path. | Timed integration test. |
| SI-11 | No deploy during market hours. | Deploy-script guard test. |
| SI-12 | Order rate provably below SEBI 10-OPS threshold. | Governor + audit-log review. |

An invariant regression is a **release blocker**, regardless of feature completeness.

---

## 3. Quality Metrics (targets)

- **Test coverage:** ≥90% overall; **100%** on `xenalgo/risk/` and `xenalgo/execution/` (safety-critical).
- **Reliability:** 100% of expected commissioning sessions accounted for; auto-recovery from an induced crash ≤60 s.
- **Latency:** signal→order-submitted ≤2 s in-window; dashboard push ≤3 s.
- **Durability:** 0 acknowledged-order losses across ≥1,000 crash-injection cycles.
- **Alerting:** 100% of orders/fills/rejections/breaker events produce an alert (no silent action).
- **Reconciliation:** 0 unresolved local-vs-broker mismatches carried overnight.

---

## 4. Business/Outcome Criteria (post-go-live, monitored not gated)

These do **not** gate the build (edge is pre-validated), but are monitored to decide continuation:
- Live per-sleeve Sharpe within a reasonable band of backtest Sharpe over a rolling quarter.
- Realized slippage ≤ modeled slippage + tolerance.
- Max realized drawdown < configured drawdown-halt (i.e., the halt was never the binding constraint by surprise).
- Cost drag (fees+slippage) within backtest assumptions.

Breach of these triggers a **review**, not an automatic halt (the breakers handle acute risk; these handle edge decay).

---

## 5. Definition of Done (per component)
A component is "done" when: interface matches TRD · unit tests pass with required coverage · relevant safety invariants tested · integrated into the monolith without breaking the startup gate · alert/log hooks present · documented in code and reflected in the traceability matrix.
