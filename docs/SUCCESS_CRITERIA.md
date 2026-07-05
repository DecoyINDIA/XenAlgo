# XenAlgo — Success Criteria & Acceptance Gates

**Version:** 1.0 · **Date:** 2026-07-04

Every criterion is **measurable and testable**. A phase gate passes only when all of its criteria are met. Criteria trace to PRD goals (G1–G6) and requirements.

---

## 1. Phase Exit Gates (must all pass)

**Current evidence snapshot (2026-07-05):** G0, G1, and the repository-local Phase 3.1
failure-injection suite are locally green. Phase 2 console behavior is covered by local
snapshot/SSE/control tests, but the Tailscale network proof still requires the Oracle paper
host. Full G3 go-live remains blocked by external/operator gates: Oracle-host proof,
four-week paper burn-in, live-host migration, Dhan static-IP registration, backup/restore
drills, live kill-switch proof, funded account setup, and staged capital ramp.

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
covered in `tests/integration/test_phase2_console.py`; deployed Tailscale/off-tailnet port
evidence is pending until the Oracle paper host exists.

### G3 — Go-Live
- [ ] Full failure-injection suite (Phase 3.1) **100%** green.
- [ ] ≥4-week paper burn-in on live data completed.
- [ ] Per-sleeve daily return deviation (paper vs backtest expectation) within **±X%** tolerance (set during burn-in, default ±0.5% abs daily) on ≥90% of days; no unexplained outliers.
- [ ] Token auto-refresh succeeded on ≥5 consecutive live sessions.
- [ ] Static IP registered & startup-verified; DH-905/invalid-IP path proven.
- [ ] Backup + **restore drill** completed successfully.
- [ ] Kill switch verified against the live broker (Trader's-Control path).
- [ ] Staged ramp complete: 10→25→50→100%, each ≥2 clean weeks.

Local status: `tests/chaos/` covers the Phase 3.1 failure list locally. The remaining G3
items require real host, broker, account, phone-alert, calendar-time, and operator evidence;
they must not be marked complete from local tests alone.

Phase 3.2 evidence support is covered locally by `tests/unit/test_phase32_readiness.py`:
burn-in records are checked for four-week span, complete sleeve reviews, deviation ratio,
token refresh success, safety incidents, and unresolved outliers; live-host evidence is
checked for India-region host selection, static-IP lead time, Docker/systemd/backups/restore,
heartbeat, Oracle warm-staging retention, and live-order toggles remaining disabled. Passing
these local checks is necessary evidence hygiene, not a substitute for the external gate.

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
- **Reliability:** ≥99% market-hours uptime during burn-in; auto-recovery from induced crash ≤60 s.
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
