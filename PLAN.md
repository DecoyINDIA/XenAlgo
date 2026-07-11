# XenAlgo — Master Plan

**Autonomous NSE swing-trading system on Dhan. Single user. Real capital. Zero human intervention in the loop — maximum human control over the loop.**

Planned 2026-07-04. Source base: `_source/` (clone of quant-swing-trade — research/backtest engine is kept; execution layer is rebuilt).

---

## 1. Objective & Non-Goals

**Objective:** A fully autonomous swing-trading bot that runs the three validated alphas (`std30`, `alpha_027`, `alpha_062`) on the NIFTY-500 universe via Dhan, with institutional-grade guardrails, a secure real-time web console, and complete auditability. Phase 2 adds a memory/learning layer.

**Non-goals (v1):** multi-user support, HFT/intraday scalping, options/F&O, other brokers, strategy invention (the 3 alphas only).

**Latency truth:** this is a daily-bar swing system. "Fast" = the bot reacts in **seconds** and never misses its execution window — not microseconds. Dhan's order engine is <25ms; an India-region VPS is 5–35ms RTT. We spend the latency budget on **correctness**: fill confirmation, reconciliation, and pre-trade checks. Colocation-style optimization is irrelevant at this cadence and will not be pursued.

**Broker & hosting (decided 2026-07-05; OCI instance started 2026-07-06):** **Dhan** stays the broker — order placement API is free, only the historical/real-time data API is paid (~₹499+tax/mo); the 3 alphas' backtests are already validated on real Dhan historical data, so switching brokers would mean re-validating edge on a different data source for no clear gain. **Oracle Cloud "Always Free"** in Mumbai/Hyderabad is the host for development and paper-trading. The first paper VM is Oracle Linux 9 on `VM.Standard.E2.1.Micro` with an ephemeral public IPv4; an A1 Flex attempt failed against the selected image. Oracle's known account-suspension risk means **live capital moves to a small paid VPS** (~$10-15/mo — AWS ap-south-1 or DO Bangalore) at the Phase 3 go-live transition; see §6.

---

## 2. Compliance Envelope (SEBI 2025 / hard constraints)

| Constraint | Value | XenAlgo response |
|---|---|---|
| Order-per-second threshold (no exchange registration needed below it) | **10 OPS/exchange/client** | Internal governor hard-caps at **2 orders/sec** — 5× margin. Monitored invariant, alert on approach. |
| Static IP for all order APIs | Mandatory; primary + secondary; **7-day change lock** | Reserve Elastic/Reserved IP at provider *before* go-live; register both IPs; never migrate infra mid-strategy without 7-day runway. |
| Access token validity | 24 hours; renewable only while active | Automated pre-market token refresh at 08:15 IST via TOTP `generateAccessToken` (pyotp); alert + halt if refresh fails. |
| White-box status | Self-built, own account → no RA license needed | Keep strategy/execution cleanly separated in code in case distribution is ever considered (that would change licensing). |
| Dhan API rate limits | Orders 25/s · non-trading 20/s · data 10/s · quote **1/s** · 7,000 orders/day | Client-side token-bucket per API class; quote calls queued at <1/s (known community pain point). |

---

## 3. Architecture

**Single Python asyncio monolith** (`xenalgo` service) — one process, one systemd unit, one log stream. This mirrors what Freqtrade/Lumibot do successfully and avoids IPC/state-sync complexity that only pays off at scale we don't have. Components are asyncio tasks communicating over in-process queues; everything that must survive a crash lives in SQLite.

```
                        ┌─────────────────────────────────────────────┐
                        │              XenAlgo Core (asyncio)         │
  Dhan REST  ◄──────────┤  BrokerGateway (httpx, token-bucket,        │
  Dhan OrderUpdate WS ◄─┤    correlationId idempotency, retries)      │
  Dhan Postback ────────►  FillListener (WS + webhook, dual channel)  │
                        │                                             │
  DuckDB (market data) ─►  DataService (panel loader, freshness gate) │
                        │  StrategyEngine (3 alpha sleeves)           │
                        │  RiskEngine  ── independent veto layer ──   │
                        │  ExecutionEngine (order state machine)      │
                        │  Reconciler (broker truth vs local state)   │
                        │  Scheduler (APScheduler, IST, XNSE calendar)│
                        │  Watchdog / KillSwitch / Breakers           │
                        │  Alerter (Telegram + Pushover)              │
                        │  Dashboard (FastAPI + HTMX + SSE)           │
                        └───────────────┬─────────────────────────────┘
                                        │
                              SQLite WAL (journal + state)
                              Tailscale-only dashboard access
```

### 3.1 Databases (final decision)

| Store | Technology | Role |
|---|---|---|
| Market data / research | **DuckDB** (existing) | Daily OHLCV panel, backtests. Single-writer discipline: only the nightly ingest task writes; all other access read-only. |
| Orders / positions / journal / config / audit | **SQLite, WAL mode, `synchronous=FULL`** | Append-only `order_events` table (event-sourced), derived `orders`, `positions`, `portfolio_snapshots`, `risk_state`, `audit_log` tables updated in the same transaction. Survives crash/power loss. |
| Cold backup | **Parquet + SQLite `.backup`** nightly → off-box object storage (S3/B2) | Restore tested monthly. |
| Hot state / pub-sub | **asyncio queues** in-process | No Redis — unjustified at single-user scale. |

Write rate is dozens of events/day; `synchronous=FULL`'s ms-level cost is irrelevant. Freqtrade's dry-run/live DB separation is adopted: paper and live use physically separate SQLite files.

### 3.2 Order lifecycle (the core rebuild)

Every order is a state machine persisted to `order_events` **before** the API call (write-ahead intent):

```
INTENT → SUBMITTED → TRANSIT/PENDING → PART_TRADED* → TRADED
                   ↘ REJECTED           ↘ CANCELLED    ↘ EXPIRED
```

- **Idempotency:** every order carries a deterministic `correlationId` = hash(date, sleeve, symbol, side, rebalance-seq). On restart, ExecutionEngine queries `/orders/external/{correlation-id}` before ever re-submitting — a crash can never double-order.
- **Fills are facts, not assumptions:** positions update only from confirmed fill events (`filledQty`, `averageTradedPrice`) via the Order Update WebSocket, with the Postback webhook as redundant channel and REST polling as tertiary fallback. `PENDING ≠ filled` — the current code's core flaw, eliminated.
- **Partial fills:** tracked natively (`PART_TRADED` with running filled qty); unfilled remainder handled by timeout policy (cancel after N minutes, re-evaluate).
- **Order type:** **marketable LIMIT orders** (last price ± collar, e.g. +0.5% for buys), never raw MARKET — a built-in price collar that caps slippage and prevents fat-fill disasters (Mizuho/Everbright class).
- **SDK posture:** pin exact `dhanhq` version; wrap its WebSocket clients in an external supervisor task that force-kills and reconnects on hang (known SDK bugs #139, #75, #65).

### 3.3 Position truth & reconciliation

- **CNC reality:** swing positions live in **holdings** (`get_holdings`), not intraday `get_positions`. Reconciler merges both. (Fixes the cloned code's would-rebuy-everything bug.)
- **Portfolio value** = cash (fund limits) + Σ holdings × LTP — not `totalBalance` alone. (Fixes the sizing bug.)
- Reconciliation runs: on startup (mandatory, trading blocked until clean), every 15 min during market hours, and post-execution. Any mismatch between local state and broker truth → **halt + alert**; the broker is always the source of truth.

### 3.4 Multi-alpha capital sleeves

The three alphas run as **independent sleeves with fixed capital allocation** (default ⅓ each — configurable). Each sleeve sizes against *its own* capital, has its own position/exposure limits and attribution. Order netting happens at the ExecutionEngine (if sleeve A sells X and sleeve B buys X, net once). This fixes the current design where all 3 alphas fight over 100% of the same capital, and preserves per-strategy performance tracking for the Phase-2 learning layer.

### 3.5 Backtest–live parity

The backtester lags signals a day and fills at close prices. Live matches it: signals computed from the latest completed daily bars; **execution window 15:00–15:20 IST** (near close, before the 15:15 square-off guard), weekly on the configured rebalance day. Data-freshness gate: if the panel's latest bar isn't the expected trading date, **no trading** — stale data acting fresh is a classic killer.

---

## 4. Guardrail Stack (defense in depth)

Lesson from every documented disaster (Knight, Everbright, Mizuho, Flash Crash): the fatal gap is always a missing *independent* check. XenAlgo's RiskEngine is a **separate module with veto power that strategy code cannot bypass** — every order passes through it, and it holds hard limits that no strategy signal can override.

**Layer 0 — Compliance governor:** ≤2 orders/sec, daily order budget, static-IP verified at startup.

**Layer 1 — Pre-trade checks (per order, all must pass):**
- Max order notional (absolute ₹ cap, config) — fat-finger stop
- Max qty vs liquidity: order ≤ 5% of 20-day ADV
- Price collar: limit price within ±3% of previous close (reject insane prices from bad data)
- Position cap: ≤10% of portfolio per symbol (existing rule, kept)
- Max positions per sleeve and global
- Sufficient-cash check with fee buffer
- Duplicate check via correlationId lookup
- Restricted-list check: symbols in ASM/GSM surveillance, upper/lower circuit at last close, or manually blacklisted → no new entries
- Symbol sanity: security-id resolution verified against fresh scrip master

**Layer 2 — Portfolio circuit breakers (continuous):**
- **Daily max loss** (default 2% of portfolio) → flatten nothing, but halt all new orders + alert
- **Max drawdown halt** (default 10% from equity peak) → halt trading entirely until manual dashboard re-arm
- **Consecutive-failure breaker:** ≥3 order rejections/errors in a session → halt + alert
- **Stale-data breaker:** panel or LTP older than tolerance → no trading
- **Reconciliation-mismatch breaker** (§3.3)

**Layer 3 — Operational:**
- **Kill switch, three paths:** dashboard button, Telegram `/kill` command, and Dhan's own **Trader's Control kill-switch API** (broker-side stop — works even if our box is compromised)
- **Dead-man watchdog:** systemd `Restart=on-failure` + external heartbeat (healthchecks.io); missed heartbeat pages via Pushover
- **No-deploy rule:** deployments blocked during market hours (enforced in deploy script) — the Knight Capital lesson
- Order timeout → auto-cancel unfilled orders at window end
- Startup gate: token valid + reconciliation clean + calendar check + config checksum, else refuse to trade
- **Trading window guards:** never trade 09:15–09:30 (opening volatility) or after 15:20; holiday calendar = `pandas_market_calendars` (XNSE) **plus** manually maintained NSE override list (muhurat sessions, ad-hoc holidays)

**Layer 4 — Blast radius:** bot runs in a **dedicated Dhan account** funded only with allocated trading capital. Worst case is bounded by construction.

**Alerting:** Telegram = every order, fill, rejection, breaker event, daily summary. Pushover (retry-until-acknowledged) = system-health criticals only (crash, token failure, heartbeat loss, breaker trips). Email = weekly audit report only.

---

## 5. Web Console (dashboard)

**Stack:** FastAPI + HTMX + SSE, server-rendered — one language, no frontend build, reuses existing Plotly reporting. Real-time push of fills/P&L/alerts via SSE.

**Security:** **Tailscale-only. Zero public ports.** The dashboard binds to the tailnet interface; access from phone/laptop via Tailscale. No auth surface exposed to the internet at all. (Dhan Postback webhook, which needs a public endpoint, is isolated on its own port with HMAC/token validation and does nothing but enqueue events.)

**Screens:** Live overview (equity, day P&L, positions, breaker states, market status) · Orders & fills (state machine view) · Per-sleeve performance vs backtest expectation · Risk panel (limit utilization, breaker arm/re-arm, **kill switch**) · Logs/audit trail · Config viewer (read-only in market hours).

---

## 6. Deployment & Ops

**Two-stage hosting (decided 2026-07-05):**

| Stage | Host | Cost | Used for |
|---|---|---|---|
| **Dev / Paper (Phase 0–3.3)** | **Oracle Cloud "Always Free"** — current paper VM is Oracle Linux 9 on `VM.Standard.E2.1.Micro` in Mumbai; A1 Flex remains a possible future resize only with a compatible ARM image | $0 forever | Build, unit/integration/chaos tests, one-week software commissioning |
| **Live capital (Phase 3.4+)** | Small paid VPS — AWS ap-south-1 or DO Bangalore, t3.micro/small equivalent | ~$10-15/mo | Real-money execution |

Rationale: Oracle's free tier is genuine (not a trial) and gives an India-region static IP at zero cost, but carries a documented risk of surprise account suspension — acceptable for development/paper where downtime costs nothing, not acceptable once real capital is live. The migration from Oracle → paid VPS is itself a static-IP change, so it must happen **≥7 days before go-live**, never mid-ramp.

| Item | Decision |
|---|---|
| Dev/paper host | Oracle Cloud Always Free, current `VM.Standard.E2.1.Micro` in Mumbai |
| Live host | AWS ap-south-1 (Mumbai) — or DO Bangalore for cost; finalize at Phase-3 start |
| IP | Current Oracle dev/paper IP is ephemeral (`80.225.212.3` at creation time) and must be re-checked after stop/start; on migration to live host, reserved/Elastic static IP ×2 (primary+secondary) registered with Dhan ≥7 days pre-go-live |
| Supervision | systemd (`Restart=on-failure`), journald logs; Docker optional for env pinning (portable across the Oracle→paid-VPS migration) |
| Secrets | `.env` outside repo, 0600, never in backups; TOTP secret + client-id only (tokens are ephemeral) |
| Backups | Nightly SQLite `.backup` + DuckDB→Parquet export → S3/B2; weekly VPS snapshot; monthly restore drill |
| Time | Everything IST-aware (`Asia/Kolkata`), NTP-synced host |
| Daily rhythm | 08:15 token refresh → 08:30 data sync + calendar/scrip-master check → 09:00 startup gate + reconcile → market-hours monitoring → 15:00–15:20 execution window (rebalance days) → 15:45 EOD sync, journal flush, Telegram summary → 02:00 backups |
| Data API cost | Dhan historical/real-time data tier: ~₹499+tax/mo (order placement API remains free) |

---

## 7. Phased Roadmap

**Phase 0 — Foundation (repo & scaffolding)**
Promote source to XenAlgo structure; keep Brain research engine + Strategies untouched; new `xenalgo/` package for the live system; config split (research vs live); pin all deps; CI running the existing test suite.

**Phase 1 — Execution core (the big one)**
SQLite journal + order state machine · Dhan BrokerGateway (httpx, rate-buckets, correlationId) · dual-channel FillListener · RiskEngine with full Layer 0–2 checks · Reconciler (holdings+positions) · sleeve-based StrategyEngine · Scheduler + calendar · token manager · Telegram/Pushover alerter. **Paper mode runs this identical pipeline** (PaperBroker upgraded to consume live LTPs) — paper and live differ only at the gateway boundary.

**Phase 2 — Console**
FastAPI+HTMX dashboard, SSE, kill switch, breaker re-arm, Tailscale deployment.

**Phase 3 — Hardening & go-live**
Failure-injection tests (kill process mid-order, drop WS mid-fill, expire token mid-session, corrupt a candle, simulate rejection storms) · **one commissioning week covering at least five consecutive NSE trading sessions** in paper mode on live market data · go-live checklist gate · staged capital ramp: 10% → 25% → 50% → 100%, each stage ≥2 clean weeks. The commissioning week validates software operation, not strategy profitability; the three strategies already have five-year backtest evidence.

**Phase 4 — Learning layer (user's "version 2")**
Trade-journal analytics feeding a memory layer (evaluate open-source options: Letta/MemGPT, mem0, Zep, or purpose-built SQLite memory); AI-API post-trade review (regime tagging, slippage analysis, per-sleeve health); parameter adaptation proposals — **always human-approved, never self-modifying live risk limits**.

---

## 8. Open Decisions (need owner's call before Phase 1 ends)

1. **Capital amount & account:** dedicated Dhan account — decision on hold (owner deferred 2026-07-04). Initial allocation for the 10% ramp stage still needed once resolved.
2. **Sleeve weights:** ⅓/⅓/⅓ or Sharpe-weighted from backtests?
3. **Breaker thresholds:** daily-loss 2% and drawdown-halt 10% are defaults — confirm risk appetite.
4. **Live-stage host:** AWS Mumbai (ecosystem) vs DO Bangalore (cost) — finalize ≥7 days before the Oracle→live migration (static-IP lock).

**Resolved:**
- ~~Broker choice~~ → **Dhan**, confirmed 2026-07-05 (backtests already validated on real Dhan historical data; Fyers considered and rejected to avoid re-validation risk).
- ~~Dev/paper host~~ → **Oracle Cloud Always Free**, confirmed 2026-07-05.
- ~~Real-data validation~~ → not applicable; **backtests were run on real Dhan API data throughout** (synthetic mode only triggers locally when no API keys are configured — confirmed by owner 2026-07-04).
- ~~Paper duration and purpose~~ → **one commissioning week covering at least five consecutive NSE trading sessions**, confirmed 2026-07-11. This validates the bot's software flow, not strategy profitability; strategy evidence comes from the existing five-year backtests.
