# XenAlgo — Product Requirements Document (PRD)

**Version:** 1.0 · **Date:** 2026-07-04 · **Owner:** Subham · **Status:** Approved for build

---

## 1. Summary

XenAlgo is a fully autonomous swing-trading system for Indian NSE equities, executing three pre-validated alpha strategies through the Dhan broker API with zero human intervention in the trading loop. It runs unattended on a Mumbai-region server, enforces institutional-grade risk controls, and exposes a secure real-time console for observation and override. The operator's role is to *supervise the machine*, not to place trades.

**Product thesis:** A single operator's edge (three backtested alphas on real Dhan data) is only worth deploying if execution is flawless and losses are bounded by construction. XenAlgo's value is not the strategies — those exist — it is the **safety, autonomy, and auditability** wrapped around them.

---

## 2. Goals & Non-Goals

### 2.1 Goals
- **G1 — Autonomy:** Run an entire trading day (token refresh → data sync → signal → execution → reconciliation → reporting) with no human action required.
- **G2 — Capital safety:** No single bug, crash, or bad data event can cause uncontrolled loss. Every documented disaster class (fat-finger, runaway loop, stale data, double-order, state drift) has a dedicated, independent control.
- **G3 — Fidelity:** Live behavior matches the validated backtest (same signals, same execution timing model, quantified deviation).
- **G4 — Observability:** The operator can see full system state, every order's lifecycle, per-strategy attribution, and risk-limit utilization in real time, and can halt everything in one action.
- **G5 — Auditability:** Every decision and order is journaled append-only and reconstructable after the fact.
- **G6 — Compliance:** Operate within SEBI's 2025 retail-algo framework without requiring exchange algo registration.

### 2.2 Non-Goals (v1)
- Multi-user / multi-account (single operator, single Dhan account).
- Intraday scalping / HFT / options / F&O / other asset classes.
- Other brokers (broker layer is abstracted for the future, but only Dhan is implemented).
- Strategy research or invention — the three alphas are fixed for v1.
- Self-modifying risk limits (learning layer in Phase 4 proposes; humans approve).

---

## 3. Personas

| Persona | Description | Primary needs |
|---|---|---|
| **Operator (Subham)** | Sole owner; capital at risk; technically capable. | Trust the bot unattended; instant visibility; one-tap kill; confidence limits hold. |
| **Auditor (Operator, retrospectively)** | Same person reviewing what happened after a bad day. | Complete, tamper-evident trade & decision history; backtest-vs-live deviation. |
| **The Bot** | The autonomous system itself. | Fresh data, valid token, clean reconciliation, unambiguous limits, safe restart. |

---

## 4. User Stories & Acceptance Criteria

### Epic A — Autonomous Operation
- **A1** *As the operator, I want the bot to refresh its Dhan token before market open automatically* so I never have to log in.
  - AC: Token refreshed via TOTP by 08:15 IST daily; on failure, trading is blocked for the day and a critical alert is sent.
- **A2** *As the operator, I want the bot to run the full rebalance cycle on scheduled days without me* .
  - AC: On a rebalance day, signals compute from the latest completed daily bars and orders execute within the 15:00–15:20 IST window; on non-rebalance days no orders are placed.
- **A3** *As the operator, I want the bot to recover safely after a crash/restart* .
  - AC: On restart the bot reconciles against broker truth and replays its journal before any new order; an in-flight order is never duplicated.

### Epic B — Capital Safety
- **B1** *As the operator, I want a hard cap on any single order's value* so a bug can't send a monstrous order.
  - AC: Any order exceeding the configured max notional is rejected pre-submission and alerted.
- **B2** *As the operator, I want the bot to stop trading if the day's loss exceeds my limit* .
  - AC: When day P&L ≤ −(daily-loss-limit), all new orders halt; existing positions are left (swing), operator alerted.
- **B3** *As the operator, I want trading to halt on a max-drawdown breach until I personally re-arm it* .
  - AC: On drawdown ≥ limit from equity peak, the bot enters HALTED state; only an explicit dashboard/Telegram re-arm resumes it.
- **B4** *As the operator, I want the bot to never act on stale or corrupt data* .
  - AC: If the latest data bar is not the expected trading date, or a price fails sanity bounds, no order referencing it is placed.
- **B5** *As the operator, I want positions to update only from confirmed fills* .
  - AC: A PENDING/accepted order never mutates tracked positions; only a confirmed fill event does.

### Epic C — Control & Observability
- **C1** *As the operator, I want a real-time console showing equity, positions, orders, and risk state* .
  - AC: Dashboard reflects a fill within 3 seconds of confirmation via server push.
- **C2** *As the operator, I want to kill all trading instantly from my phone* .
  - AC: Kill switch reachable via dashboard, Telegram command, and broker-side API; activating any one blocks all further order submission within 1 second.
- **C3** *As the operator, I want an alert for every order, fill, rejection, and breaker event* .
  - AC: Telegram message dispatched for each such event; system-health criticals additionally go to Pushover with acknowledgement.
- **C4** *As the operator, I want per-strategy performance vs backtest expectation* .
  - AC: Each alpha sleeve shows its own P&L, positions, and deviation from backtested return.

### Epic D — Compliance & Audit
- **D1** *As the operator, I want to stay below the SEBI algo-registration threshold automatically* .
  - AC: Outgoing order rate is hard-capped at ≤2 orders/sec; the cap is monitored and can never be exceeded by strategy logic.
- **D2** *As the auditor, I want a complete, append-only record of every decision and order* .
  - AC: `order_events` is insert-only; current state is derivable by replay; no event is ever updated or deleted.

---

## 5. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Automated daily Dhan token refresh via TOTP before market open. | P0 |
| FR-2 | Market-calendar-aware scheduler (IST, XNSE + manual override list). | P0 |
| FR-3 | Load daily OHLCV panel from DuckDB with a freshness gate. | P0 |
| FR-4 | Compute the three alphas as independent capital sleeves. | P0 |
| FR-5 | Portfolio construction per sleeve (existing engine, sleeve-scoped capital). | P0 |
| FR-6 | Order state machine with write-ahead intent and correlationId idempotency. | P0 |
| FR-7 | Dhan BrokerGateway: place/modify/cancel + funds/holdings/positions, rate-limited. | P0 |
| FR-8 | Dual-channel fill confirmation (Order Update WS + Postback webhook + REST fallback). | P0 |
| FR-9 | RiskEngine independent pre-trade check battery (Layer 1). | P0 |
| FR-10 | Portfolio circuit breakers (daily loss, drawdown, consecutive failure, stale data, reconciliation). | P0 |
| FR-11 | Reconciler merging holdings + positions against local state on startup and periodically. | P0 |
| FR-12 | Kill switch across three independent paths. | P0 |
| FR-13 | Paper-trading mode running the identical pipeline against a simulated broker. | P0 |
| FR-14 | Alerter: Telegram (events) + Pushover (criticals) + email (weekly). | P1 |
| FR-15 | FastAPI + HTMX + SSE dashboard, Tailscale-only. | P1 |
| FR-16 | Append-only SQLite journal + derived state tables; nightly backups off-box. | P0 |
| FR-17 | EOD reporting: journal flush, daily summary, backtest-vs-live deviation. | P1 |
| FR-18 | Config management with market-hours change lock and startup checksum. | P1 |
| FR-19 | Restricted-list ingestion (ASM/GSM, circuit, manual blacklist) feeding pre-trade checks. | P1 |
| FR-20 | (Phase 4) Learning layer: post-trade analytics + human-approved parameter proposals. | P2 |

---

## 6. Non-Functional Requirements

- **NFR-1 Reliability:** ≥99% uptime during market hours; auto-restart on failure; safe restart guaranteed.
- **NFR-2 Latency:** signal→order-submitted ≤2s within the execution window; dashboard push ≤3s. (Correctness > speed; no HFT targets.)
- **NFR-3 Durability:** zero acknowledged-order loss across crash/power failure (`synchronous=FULL` journal).
- **NFR-4 Security:** no public inbound ports except the isolated, authenticated Postback webhook; secrets 0600, outside repo, excluded from backups.
- **NFR-5 Recoverability:** full state restore from off-box backup verified monthly; RPO ≤24h, RTO ≤1h.
- **NFR-6 Auditability:** 100% of orders traceable from intent to terminal state.
- **NFR-7 Compliance:** provably ≤10 OPS; static IP registered; no exchange algo ID required.
- **NFR-8 Testability:** every risk control and state transition covered by an automated test; failure-injection suite for crash/disconnect/token-expiry/bad-data.

---

## 7. Assumptions & Constraints
- Single dedicated Dhan account, funded only with allocated trading capital (bounded blast radius).
- Static IP with a 7-day change lock — infra chosen ≥7 days before go-live.
- Dhan tokens are 24h and refreshable only while active.
- Daily-bar swing cadence — colocation/microsecond optimization out of scope.
- The three alphas are validated on real Dhan historical data and fixed for v1.

## 8. Risks (product-level)
| Risk | Mitigation |
|---|---|
| Strategy edge decays post-deployment | Per-sleeve live-vs-backtest deviation monitoring; drawdown halt; Phase-4 review. |
| Dhan API outage during window | Retry/backoff; missed-window is safe (no partial rebalance committed); alert. |
| Operator over-trusts autonomy | Mandatory alerts on every action; weekly review ritual; staged capital ramp. |
| Static-IP misconfiguration blocks orders | Startup IP-verification gate; DH-905 detection; secondary IP. |

## 9. Success Metrics
See `SUCCESS_CRITERIA.md`. Headline: one live-market paper commissioning week covering at least five consecutive NSE trading sessions, with clean scheduling, data, signals, risk decisions, fills, reconciliation, journaling, alerts, restart recovery and kill-switch behaviour before any real capital. This is a software commissioning gate, not a repeat of strategy validation; the strategies already have five-year backtest evidence.
