# XenAlgo — Phased Build Plan

**Version:** 1.0 · **Date:** 2026-07-04 · **Companion to:** `PRD.md`, `TRD.md`

Each phase has an explicit **exit gate** — the next phase does not start until the gate passes. Gates map to `SUCCESS_CRITERIA.md`. Effort is relative (S/M/L), not calendar-committed.

---

## Phase 0 — Foundation & Scaffolding
**Goal:** Clean, buildable XenAlgo project with the research engine intact and CI green.

| # | Task | Effort |
|---|---|---|
| 0.1 | Promote `_source/` into XenAlgo layout: keep `Brain/` (research/backtest) and `Strategies/` verbatim; add empty `xenalgo/` package for the live system. | S |
| 0.2 | Split config: `config.research.yaml` (backtest) vs `config.live.yaml` (execution/risk/sleeves/governor per TRD §5). | S |
| 0.1a | Provision Oracle Cloud Always Free instance in Mumbai/Hyderabad, attach a public IP, install Tailscale, close all inbound ports except SSH. Current paper VM was created 2026-07-06 as Oracle Linux 9 on `VM.Standard.E2.1.Micro` after the selected image failed on A1 Flex; the `Dockerfile` keeps the app portable to the future paid-VPS host unchanged. | S |
| 0.3 | Pin all deps to exact versions (incl. `dhanhq==2.0.2`, `pytz`, `scipy`); add `pandas_market_calendars`, `apscheduler`, `httpx`, `pyotp`, `fastapi`, `uvicorn`, `python-telegram-bot`. Lockfile. | S |
| 0.4 | Test harness: `tests/` dir, pytest config, move/extend existing `Lab` coverage into repo-local tests; CI runs the committed repo suite on every change. | S |
| 0.5 | Structured logging + run-id context; `.env.example`; secrets hygiene (.gitignore, 0600). | S |

**Exit Gate G0:** `pytest` green (existing 4 + new scaffolding), project imports cleanly, config loads both profiles, CI passes.

---

## Phase 1 — Execution Core (the critical phase)
**Goal:** The full autonomous pipeline works end-to-end in **paper mode**, with all P0 safety controls active. Paper and live differ only at the gateway boundary.

Build order is dependency-driven and each sub-step is independently testable:

| # | Task | Effort | Key tests |
|---|---|---|---|
| 1.1 | **SQLite journal + state model** (TRD §3): schema, WAL/FULL, append-only `order_events`, derived-state updater, replay self-check. | M | journal durability, replay==derived, idempotent apply |
| 1.2 | **Order state machine**: transitions, guards, persistence, restart replay. | M | every legal/illegal transition; restart mid-state |
| 1.3 | **RiskEngine** (pure): all Layer-1 checks + Layer-2 breaker logic + state persistence. | L | one test per check; breaker arm/trip/re-arm |
| 1.4 | **Governor**: token-bucket rate limits (orders ≤2/s, quote ≤1/s, daily cap). | S | never exceeds cap under burst |
| 1.5 | **BrokerGateway (Dhan)**: place/modify/cancel + funds/holdings/positions; correlationId idempotency; marketable-limit; error mapping; retry policy. Behind `BrokerInterface`. | L | idempotent re-submit; DH-905 handling; mock-broker contract |
| 1.6 | **PaperBroker v2**: implements `BrokerInterface`, fills against live/last LTP with existing cost model, honors same code path. | M | fill accounting, cost parity with backtest |
| 1.7 | **FillListener**: WS + Postback + REST fallback, dedup, idempotent journal application. | M | duplicate fill no-op; WS drop → REST recovers |
| 1.8 | **Reconciler**: holdings+positions merge, portfolio value, mismatch breaker, startup block. | M | drift detection; CNC-in-holdings correctness |
| 1.9 | **DataService freshness + price sanity** gates. | S | stale date blocks; NaN/insane price blocks |
| 1.10 | **StrategyEngine sleeves**: 3 alphas, fixed capital fractions, per-sleeve sizing + attribution. | M | sleeve capital isolation; netting across sleeves |
| 1.11 | **ExecutionEngine**: deltas, SELL-before-BUY, min-holding, order timeout, kill-switch check. | L | sequencing; timeout cancel; kill halts submission |
| 1.12 | **TokenManager**: TOTP refresh, persistence, RenewToken backup, startup `ensure_valid`. | M | refresh success/fail path; expiry handling |
| 1.13 | **Scheduler**: APScheduler IST, XNSE calendar + overrides, window/holiday guards. | M | rebalance-day logic; holiday skip; window guard |
| 1.14 | **Alerter**: Telegram events + Pushover criticals (email deferred). | S | dispatch on each event type; failure non-blocking |
| 1.15 | **Wire the monolith**: asyncio orchestration, startup gate, graceful shutdown/square-off hook. | M | startup gate blocks on any failed precondition |

**Exit Gate G1:** In paper mode, a full simulated trading day runs unattended: token refresh → data freshness → sleeve signals → risk-checked orders → confirmed fills → reconciliation → journal → alerts. All P0 controls demonstrably active. Failure-injection subset (crash mid-order, duplicate fill, stale data) handled safely. Coverage: 100% of risk checks and state transitions.

---

## Phase 2 — Console
**Goal:** Real-time observability and control.

| # | Task | Effort |
|---|---|---|
| 2.1 | FastAPI app skeleton, SSE channel, HTMX base templates. | M |
| 2.2 | Screens: overview, orders/fills, per-sleeve performance, risk panel, logs/audit, config view. | L |
| 2.3 | Kill-switch endpoint + breaker re-arm (authenticated actions, audit-logged). | S |
| 2.4 | Telegram command interface (`/status`, `/kill`, `/positions`, `/rearm`). | M |
| 2.5 | Tailscale deployment; isolated Postback webhook endpoint (HMAC). | M |

**Exit Gate G2:** Dashboard reflects paper fills ≤3s; kill switch (all three paths) halts submission ≤1s; reachable only over Tailscale; no public ports except validated webhook.

---

## Phase 3 — Hardening & Go-Live
**Goal:** Prove safety under adversity, then ramp real capital.

| # | Task | Effort |
|---|---|---|
| 3.1 | **Failure-injection suite** (full): kill process mid-order, drop WS mid-fill, expire token mid-session, corrupt a candle, rejection storm, reconciliation drift, network partition, clock skew. Runs on the Oracle dev host. | L |
| 3.2a | **One-week software commissioning** on live market data, still on Oracle Cloud Always Free: at least five consecutive NSE trading sessions proving unattended scheduling, data freshness, three-sleeve signals, risk decisions, paper fills, reconciliation, journaling, alerts, restart recovery, and kill-switch behaviour. Weekly profit is not a pass/fail criterion because the strategies already have five-year backtest evidence. | M |
| 3.2b | Choose live host (AWS ap-south-1 vs DO Bangalore); provision paid VPS; deploy the same Docker image; register static IPs with Dhan **≥7 days before go-live**; systemd; backups + monthly restore drill; heartbeat. Oracle instance is retained as a warm dev/staging box, not decommissioned. | M |
| 3.3 | Run focused paper-mode deployment-parity and startup checks **on the new live host** after migration (new IP, new box) before touching real capital. Repeat any failed commissioning control; another fixed calendar week is not required when the full Oracle commissioning week passed and the same image/config checksum is deployed. | S |
| 3.4 | Go-live checklist gate (below); enable `live_trading` with **10% capital**. | S |
| 3.5 | **Staged capital ramp:** 10% → 25% → 50% → 100%, each stage ≥2 clean weeks (no safety incident, deviation within tolerance). | L |

Repository-local Phase 3.2 support now lives in `xenalgo.phase32` and
`docs/PHASE3_2_OPERATIONS.md`. It evaluates supplied commissioning and live-host evidence, but
does not replace the required five-session commissioning run, host provisioning, Dhan static-IP
registration, restore drill, or heartbeat proof.

Repository-local Phase 3.3 support now lives in `xenalgo.phase33` and
`docs/PHASE3_3_OPERATIONS.md`. It evaluates supplied post-migration paper-validation
evidence from the paid live host. Its current evaluator retains the legacy one-week
threshold and must be updated for the focused deployment-parity decision. It does not
replace new-host operation, static-IP startup proof, checksum verification, or operator
review.

Repository-local Phase 3.4 support now lives in `xenalgo.phase34` and
`docs/PHASE3_4_OPERATIONS.md`. It evaluates the supplied go-live checklist evidence for
the initial 10% live-capital stage, but does not call Dhan, mutate config, fund the
account, verify phone alerts, or replace explicit operator approval to enable live order
placement.

Repository-local Phase 3.5 support now lives in `xenalgo.phase35` and
`docs/PHASE3_5_OPERATIONS.md`. It evaluates supplied staged-ramp evidence for
10% -> 25% -> 50% -> 100% capital, but does not call Dhan, mutate config, advance capital,
or replace the required two clean live weeks at each stage.

**Go-Live Checklist (all mandatory):** G0–G2 passed · full failure-injection suite green · one commissioning week with ≥5 consecutive reviewed NSE sessions and zero unresolved software/safety failures · post-migration deployment-parity checks on the paid live host green · static IP registered & verified on the live host · token auto-refresh proven over ≥5 sessions · backups + restore drill done on the live host · kill switch verified live · dedicated funded account · alerts confirmed on real phone.

**Exit Gate G3:** Live at 100% capital, ≥2 clean weeks per stage, zero safety incidents, live-vs-backtest deviation within tolerance.

---

## Phase 4 — Learning Layer (v2)
**Goal:** Self-improvement from trade history — humans approve, system never self-modifies live limits.

| # | Task | Effort |
|---|---|---|
| 4.1 | Trade-journal analytics: per-sleeve attribution, slippage vs model, regime tagging, alpha-decay tracking. | L |
| 4.2 | Evaluate/integrate a memory layer (Letta/MemGPT, mem0, Zep, or SQLite-native). | M |
| 4.3 | AI-API post-trade review producing structured insights + parameter-change *proposals*. | M |
| 4.4 | Human-approval workflow in dashboard; approved changes versioned via `config_versions`. | M |

**Exit Gate G4:** System produces reviewed, actionable proposals; no proposal alters live risk limits without explicit operator approval.

---

## Dependency Graph (phase-level)
`P0 → P1 → {P2, P3.1} → P3.2 → P3.3 → P3.4 → P3.5 → P4`
(P2 console and P3.1 failure-injection can proceed in parallel once P1's core is stable.)
