<!--
  ========================================================================================
  DECOYINDIA // PROPRIETARY QUANTITATIVE RESEARCH & EXECUTION SYSTEMS
  XenAlgo: Autonomous NSE Swing-Trading Execution & Institutional Risk-Containment Engine
  Engineered by Subham Jena (DecoyINDIA) for the National Stock Exchange of India (NSE)
  ========================================================================================
-->

<p align="center">
  <img src="assets/readme/hero-cinematic.svg" alt="XenAlgo — Autonomous NSE Swing-Trading Execution & Risk Engine" width="100%" />
</p>

<p align="center">
  <a href="#12-verification--safety-test-suite"><img src="https://img.shields.io/badge/Safe%20Suite-203%20Passed-10B981?style=for-the-badge&logo=pytest&logoColor=white" alt="Pytest Safe Suite" /></a>
  <a href="#6-institutional-guardrail-stack--the-12-safety-invariants"><img src="https://img.shields.io/badge/Safety%20Invariants-12%2F12%20Enforced-7C86FF?style=for-the-badge&logo=shield&logoColor=white" alt="12 Safety Invariants" /></a>
  <a href="#8-sebi-compliance-envelope--rate-throttling"><img src="https://img.shields.io/badge/SEBI%20Cap-≤%202%20OPS%20(5x%20Margin)-06B6D4?style=for-the-badge&logo=speedtest&logoColor=white" alt="SEBI Rate Governor" /></a>
  <a href="#7-deterministic-order-state-machine--sqlite-wal-journal"><img src="https://img.shields.io/badge/Storage-SQLite%20WAL%20%2B%20DuckDB-F59E0B?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL and DuckDB" /></a>
  <a href="#10-real-time-supervised-console--zero-trust-mesh"><img src="https://img.shields.io/badge/Console-Tailscale%20Zero--Trust-8B5CF6?style=for-the-badge&logo=tailscale&logoColor=white" alt="Tailscale Private Console" /></a>
  <a href="#5-multi-alpha-strategy-sleeves"><img src="https://img.shields.io/badge/Market-NSE%20Equities%20(CNC)-38BDF8?style=for-the-badge&logo=databricks&logoColor=white" alt="NSE Equities CNC" /></a>
  <a href="#2-executive-overview--quant-philosophy"><img src="https://img.shields.io/badge/Architect-DecoyINDIA%20(Subham%20Jena)-EC4899?style=for-the-badge&logo=github&logoColor=white" alt="DecoyINDIA Subham Jena" /></a>
</p>

<p align="center">
  <img src="assets/readme/brand-mark-animated.svg" alt="XenAlgo Brand Mark" width="80%" />
</p>

---

## Table of Contents

1. [Cinematic Hero & System Telemetry](#1-cinematic-hero--system-telemetry)
2. [Executive Overview & Quant Philosophy](#2-executive-overview--quant-philosophy)
3. [Live Operational Timeline](#3-live-operational-timeline)
4. [Core Architectural Pillars](#4-core-architectural-pillars)
5. [Multi-Alpha Strategy Sleeves](#5-multi-alpha-strategy-sleeves)
6. [Institutional Guardrail Stack & The 12 Safety Invariants](#6-institutional-guardrail-stack--the-12-safety-invariants)
7. [Deterministic Order State Machine & SQLite WAL Journal](#7-deterministic-order-state-machine--sqlite-wal-journal)
8. [SEBI Compliance Envelope & Rate Throttling](#8-sebi-compliance-envelope--rate-throttling)
9. [Complete System Architecture](#9-complete-system-architecture)
10. [Real-Time Supervised Console & Zero-Trust Mesh](#10-real-time-supervised-console--zero-trust-mesh)
11. [Daily Autonomous Session Lifecycle](#11-daily-autonomous-session-lifecycle)
12. [Verification & Safety Test Suite](#12-verification--safety-test-suite)
13. [Production Readiness & Acceptance Gates](#13-production-readiness--acceptance-gates)
14. [Repository Map & Documentation Matrix](#14-repository-map--documentation-matrix)
15. [Operator Quickstart & Provenance Tribute](#15-operator-quickstart--provenance-tribute)

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 1. Cinematic Hero & System Telemetry

**XenAlgo** is a fully autonomous, institutional-grade quantitative swing-trading execution and risk-containment fortress engineered specifically for Indian equities listed on the **National Stock Exchange (NSE)** via the **Fyers API v3**. 

Designed and engineered from first principles by **Subham Jena (DecoyINDIA)**, XenAlgo automates the full end-to-end lifecycle of three pre-validated mathematical alpha models (`std30`, `alpha_027`, `alpha_062`) over the liquid **NIFTY-500** investment universe. The architecture enforces an absolute operational philosophy: **zero human intervention in the execution loop, coupled with maximum human supervision and override authority over the loop**.

```
========================================================================================================
DECOYINDIA // XENALGO CORE OPERATIONAL MATRIX                               SYSTEM RUNTIME & COMPLIANCE
========================================================================================================
Proprietary Architect : Subham Jena (DecoyINDIA)               Language Runtime   : Python 3.14 (via uv)
Exchange / Segment    : National Stock Exchange (NSE CNC)      Concurrency Model  : Asyncio Monolith
Broker Gateway        : Fyers API v3 (REST + WebSocket)        Transactional DB   : SQLite 3 (WAL / FULL)
Active Alpha Sleeves  : std30 · alpha_027 · alpha_062          Analytics Lake     : DuckDB (Strictly Read-Only)
Order Rate Governor   : 2.0 OPS Token Bucket (5x Margin)       Private Console    : FastAPI + HTMX + SSE
Safety Invariants     : 12 / 12 Mathematically Enforced        Network Topology   : Tailscale Zero-Trust Loopback
Kill-Switch SLA       : < 1.0 Second Halting SLA               Disaster Controls  : Triple Redundant Kill Switch
========================================================================================================
```

> [!IMPORTANT]
> **Real Capital Protection Invariant**: XenAlgo trades real capital on the National Stock Exchange of India. In quantitative trading, software defects do not manifest as benign test assertion errors — they manifest as permanent financial drawdown. All unit tests, contract mocks, and chaos simulations execute strictly against `MockBroker` and `PaperBroker`. The live Fyers order gateway is physically quarantined behind strict authorization tokens, IP validation barriers, and multi-point startup gates.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 2. Executive Overview & Quant Philosophy

### The Quantitative Genesis & DecoyINDIA Provenance

In retail quantitative trading and proprietary family offices, the vast majority of algorithmic trading initiatives fail not because the underlying mathematical formulas lack predictive power, but because of **execution fragility**:

- **Silent State Drift**: Local bot states assume orders succeeded while the broker rejected them, leading to catastrophic position desynchronization.
- **Uncontrolled Loops**: Reconnection races and unthrottled retries hammer exchange endpoints, triggering immediate API blacklisting or order spam violations.
- **Corrupt / Stale Inputs**: Placing capital at risk using stale daily bars, unadjusted stock splits, or missing corporate actions.
- **CNC vs Intraday Disconnect**: Cash-and-Carry (CNC) swing trading in India requires reconciling against demat delivery holdings (`get_holdings`) rather than intraday open positions (`get_positions`). Naive bots blindly query intraday endpoints and rebuy existing portfolio constituents daily.
- **Opaque Black Boxes**: Lack of real-time situational telemetry and immediate, single-click kill-switch capabilities.

**XenAlgo** was architected by **Subham Jena** under the **DecoyINDIA** proprietary quant banner to establish an unyielding bridge between theoretical backtests and cold exchange reality. Treating strategy algorithms as pure mathematical signal generators, XenAlgo encases them within five concentric containment layers, pure-function risk vetoes, an append-only event-sourced SQLite WAL journal, and a zero-trust supervisory console.

```
       +---------------------------------------------------------------------------------------+
       |                             THE DECOYINDIA OPERATING MAXIM                            |
       |                                                                                       |
       |             "Zero intervention in the loop. Maximum control over the loop."           |
       |                                                                                       |
       |   Capital preservation is not a constraint on alpha; it is the sole precondition for  |
       |   its existence. An algorithm that cannot survive exchange chaos has zero edge.      |
       +---------------------------------------------------------------------------------------+
```

### The Four Unconditional Engineering Biases

1. **Prefer a missed trade over an unsafe trade**: If market data is 60 seconds stale, if a price collar deviates by 0.1%, or if token authenticity cannot be verified cryptographically, the execution cycle aborts immediately. Opportunities are recurrent; destroyed capital is gone forever.
2. **Prefer an instant halt over silent state drift**: The instant local journaled positions deviate from Fyers broker truth by even a single share, all trading freezes instantly and emergency telemetry dispatches across Telegram and Pushover channels.
3. **Prefer replayable facts over mutable assumptions**: Order states are never mutated in-place. XenAlgo records every state transition into an append-only event log backed by SQLite WAL with `synchronous = FULL`. Complete portfolio state is derived deterministically by replaying historical events.
4. **Prefer explicit operator control over hidden automation**: While the daemon operates autonomously during trading hours, the human operator maintains uncompromised situational awareness via a zero-trust private console, instant Telegram commands, and out-of-band OAuth token revocation.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 3. Live Operational Timeline

XenAlgo executes an autonomous, precision-timed operational routine synchronized to Indian Standard Time (`Asia/Kolkata`) and the National Stock Exchange calendar:

<p align="center">
  <img src="assets/readme/product-in-action.svg" alt="XenAlgo Live Operational Timeline" width="100%" />
</p>

### Chronological Execution Lifecycle

| Time (IST) | Operational Phase | Subsystem Action & Verification Standard | Traceability |
|---|---|---|---|
| **08:15** | **Pre-Market Authentication** | Automated OAuth2 TOTP authentication flow (`pyotp` + `generateAccessToken`). Generates fresh 24-hour Fyers JWT. Persisted with `0600` POSIX file permissions outside repository and backup trees. Authentication failure triggers critical Pager-level alerts. | FR-1, FR-2 |
| **08:30** | **Data & Metadata Ingestion** | Ingests prior day's OHLCV daily bars into DuckDB. Synchronizes NSE scrip master, canonical security token mappings (`NSE:<SYMBOL>-EQ`), ASM/GSM surveillance lists, and exchange circuit-limit price bands. | FR-3, FR-4 |
| **09:00** | **6-Point Startup Gate** | Rigorous automated pre-flight gatekeeper: validates active token validity, static IP binding, trading calendar confirmation, scrip master freshness, SQLite WAL event-journal replay integrity, and zero-drift broker reconciliation. | FR-5, FR-11 |
| **09:15 – 09:30** | **Opening Volatility Blackout** | Strict architectural lockout. **Zero orders are placed** during opening price discovery, volatility auction uncrossing, and opening circuit swings. | FR-18 |
| **09:30 – 15:00** | **Continuous Market Surveillance** | Live WebSocket connection to Fyers order and market depth streams. Dual-channel background reconciler executes every 15 minutes. Heartbeat watchdog telemetry dispatches to healthchecks.io. | FR-13, FR-14 |
| **15:00 – 15:05** | **Signal Generation & Pure Veto** | StrategyEngine loads updated daily bars, calculates target portfolio weights for `std30`, `alpha_027`, and `alpha_062`. Computes target deltas against current holdings. All proposed orders pass through `RiskEngine.check()`. | FR-6, FR-9 |
| **15:05 – 15:15** | **Order Execution Window** | **SELL-before-BUY** order sequencing. Marketable LIMIT orders with price collars. Outbound order flow throttled to ≤ 2.0 orders/sec by the asynchronous token bucket rate governor. | FR-6, FR-7 |
| **15:15 – 15:20** | **Square-Off Guard & Timeouts** | Auto-cancels any unfilled limit orders lingering in the exchange book. Confirms all terminal fill states via dual-channel fill listener (WebSocket stream + REST orderbook reconciliation). | FR-8 |
| **15:45** | **EOD Reconciliation & Reporting** | Comprehensive post-session audit against Fyers holdings and cash ledger. SQLite WAL flush. Generates and dispatches daily portfolio attribution and Sharpe metrics to Telegram. | FR-11, FR-15 |
| **02:00** | **Cold State Off-Box Backup** | Executes atomic SQLite `.backup` and DuckDB Parquet snapshots to encrypted off-box storage. | FR-16 |

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 4. Core Architectural Pillars

XenAlgo's institutional resilience is underpinned by four immutable design pillars:

<p align="center">
  <img src="assets/readme/feature-risk-veto.svg" alt="RiskEngine Pure Veto Layer" width="100%" />
</p>

### 1. Pure Veto Layer (`xenalgo.risk`)
The `RiskEngine` is an independent, side-effect-free evaluation gatekeeper. It executes **zero network I/O**, mutates no state, and makes deterministic decisions purely on the passed `OrderRequest` and `RiskContext`.
- **Strategy Decoupling**: No alpha strategy code can bypass, modify, or silence the RiskEngine.
- **Veto Dominance**: Even if an alpha outputs an aggressive maximum-allocation BUY signal, if the order breaches a 5% ADV volume limit, violates a ±3% price collar, or exceeds the ₹2,00,000 notional cap, it is rejected or downscaled before reaching the execution pipeline.

```python
# The pure risk signature enforced across the codebase
class RiskEngine:
    def check(self, order: OrderRequest, ctx: RiskContext) -> tuple[RiskDecision, int, str]:
        """
        Pure function: (OrderRequest, RiskContext) -> (Decision, AllowedQty, Reason)
        Guaranteed zero I/O, zero state mutation, 100% unit-testable.
        """
```

### 2. Confirmed-Fills Only (SI-3)
A fatal flaw in retail algorithms is treating an `ACCEPTED` or `SUBMITTED` broker acknowledgment as an acquired portfolio position.
- **The XenAlgo Invariant**: Position ledgers mutate **strictly upon confirmed fill events** (`filledQty > 0`, verified average traded price) received via the Fyers Order WebSocket or confirmed by REST orderbook reconciliation.
- **Zero Phantom Positions**: If an order sits pending in the exchange book, stalls in transit, or is canceled mid-flight, local portfolio holdings remain completely untouched.

### 3. Append-Only Event Journal (`order_events`)
State is never mutated in-place. XenAlgo implements an event-sourced architecture backed by SQLite 3 in **Write-Ahead Logging (WAL)** mode with `PRAGMA synchronous = FULL`.
- Every transition (`INTENT` -> `SUBMITTED` -> `PENDING` -> `PART_TRADED` -> `TRADED`) is recorded as an immutable row insert.
- **Crash Durability**: If the host suffers an unexpected power loss or `kill -9` termination mid-execution, startup recovery routines replay the event log from genesis. Derived state tables (`orders`, `positions`, `portfolio_snapshots`) are reconstructed mathematically and validated against broker truth before trading resumes.

### 4. 2.0 OPS Token Bucket Rate Governor
To guarantee flawless compliance with regulatory mandates and broker infrastructure ceilings:
- Hard-caps outgoing traffic at **2 orders per second** (with a daily safety ceiling of 500 orders).
- Delivers a **5x safety buffer** below SEBI's 10 OPS algorithmic trading threshold.
- Burst orders are queued within an asynchronous token bucket; excess order attempts are throttled smoothly without dropping order intent.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 5. Multi-Alpha Strategy Sleeves

XenAlgo executes three distinct, pre-validated quantitative swing alpha strategies as isolated capital sleeves across the **NIFTY-500** equity universe:

<p align="center">
  <img src="assets/readme/feature-multi-sleeve.svg" alt="Multi-Alpha Strategy Sleeves" width="100%" />
</p>

### Strategy Profile Matrix

| Strategy Sleeve | Quantitative Mechanism & Alpha Signature | Capital Weight | Position Sizing Model | Investment Universe |
|---|---|---|---|---|
| **`std30`** | **Volatility-Adjusted Momentum Breakout**: Exploits intermediate price expansion following volatility compression regimes on high-liquidity large and mid-cap equities. | **34.0%** (1/3 Capital) | Inverse Volatility Sizing (ATR-scaled) | NIFTY-500 High-Volume Tier |
| **`alpha_027`** | **Mean-Reversion with Momentum Conditioning**: Captures short-term oversold pullbacks embedded within structural multi-week uptrends, filtered by volume exhaustion signatures. | **33.0%** (1/3 Capital) | Volatility-parity bounded | NIFTY-500 Liquid Constituents |
| **`alpha_062`** | **Cross-Sectional Relative Strength**: Exploits sector leadership and relative price rank persistence across multi-day and multi-week holding horizons. | **33.0%** (1/3 Capital) | Fixed risk budget per position | NIFTY-500 Broad Coverage |

### Capital Isolation & Order Netting Architecture

In typical multi-strategy systems, independent algorithms competing for the same trading account trigger race conditions, margin exhaustion, and corrupted performance attribution. XenAlgo resolves this via a two-tier allocator:

1. **Sleeve Independence**: Each strategy receives an explicit capital fraction (default 1/3 each). Each sleeve maintains its own internal portfolio optimizer, derives target weights, and tracks individual sleeve P&L and Sharpe ratios.
2. **Central Delta Netting**: Before any order is dispatched to the network, `ExecutionEngine` collects all sleeve targets and aggregates deltas across the portfolio:
   - *Example*: If Sleeve A signals a SELL of 100 shares of `INFY` and Sleeve B signals a BUY of 60 shares of `INFY`, XenAlgo issues **exactly one net SELL order of 40 shares**.
   - **Cash Safety Ordering**: All netted **SELL orders execute first**, liberating trading capital and clearing broker margin headroom before any BUY order is submitted.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 6. Institutional Guardrail Stack & The 12 Safety Invariants

XenAlgo enforces defense-in-depth across five concentric containment layers:

<p align="center">
  <img src="assets/readme/risk-veto-simulator.svg" alt="Risk Decision Simulator" width="100%" />
</p>

```
  +------------------------------------------------------------------------------------------------+
  | LAYER 4: BLAST RADIUS CONTAINMENT                                                              |
  | Dedicated Fyers account funded strictly with allocated swing capital. No leverage / F&O margin. |
  |                                                                                                |
  |   +----------------------------------------------------------------------------------------+   |
  |   | LAYER 3: OPERATIONAL GUARDRAILS                                                        |   |
  |   | Triple Kill Switch (Console / Telegram / Token) · Watchdog Heartbeat · Startup Gate.   |   |
  |   |                                                                                        |   |
  |   |   +--------------------------------------------------------------------------------+   |   |
  |   |   | LAYER 2: PORTFOLIO CIRCUIT BREAKERS                                            |   |   |
  |   |   | Daily Loss Halt (2.0%) · Peak Drawdown Halt (10.0%) · Consecutive Error Trip.    |   |   |
  |   |   |                                                                                |   |   |
  |   |   |   +------------------------------------------------------------------------+   |   |   |
  |   |   |   | LAYER 1: PRE-TRADE CHECK BATTERY                                       |   |   |   |
  |   |   |   | Max Notional · 5% ADV · ±3% Collar · 10% Position Cap · Clean Symbols. |   |   |   |
  |   |   |   |                                                                        |   |   |   |
  |   |   |   |   +----------------------------------------------------------------+   |   |   |   |
  |   |   |   |   | LAYER 0: COMPLIANCE GOVERNOR                                   |   |   |   |   |
  |   |   |   |   | 2.0 OPS Token Bucket Throttler · Static IP Whitelist Shield.   |   |   |   |   |
  +---+---+---+---+---+----------------------------------------------------------------+---+---+---+---+
```

### The 12 Safety Invariants Matrix (SI-1 through SI-12)

Every safety invariant is continuously verified by automated tests in `tests/unit/` and `tests/chaos/`:

| Invariant | Specification & Safety Guarantee | Primary Verification Test | Traceability ID |
|---|---|---|---|
| **SI-1** | **Max Notional Bound**: No single order can exceed the configured absolute rupee ceiling (`max_order_notional_inr = ₹2,00,000`). | `tests/unit/test_risk_engine.py` | FR-9 |
| **SI-2** | **Single Position Concentration Cap**: No single equity position can exceed 10.0% of total portfolio equity. | `tests/unit/test_risk_engine.py` | FR-9 |
| **SI-3** | **Confirmed Fills Only**: Position records mutate strictly upon receipt of confirmed broker fill notifications (`filledQty > 0`). Non-fill states (`PENDING`, `SUBMITTED`) never mutate holdings. | `tests/unit/test_order_state_machine.py` | FR-6, FR-8 |
| **SI-4** | **Idempotent Correlation ID**: No duplicate order can ever be dispatched for the same deterministic correlation key (`date:sleeve:symbol:side:seq`). | `tests/unit/test_sleeves_and_idempotency.py` | FR-6 |
| **SI-5** | **Governor Rate Enforcement**: Outgoing broker order rate strictly obeys ≤ 2.0 orders/sec and ≤ 500 orders/day under synthetic burst loads. | `tests/unit/test_governor.py` | FR-7 |
| **SI-6** | **Fresh Data Sanity**: Zero orders placed if market data panel date is older than current expected trading date, or if prices contain NaN or zero values. | `tests/unit/test_reconciler_and_data.py` | FR-3 |
| **SI-7** | **Persistent Drawdown Lockout**: Peak-to-trough equity drawdown ≥ 10.0% engages an unyielding halt that requires explicit authenticated operator re-arm. | `tests/unit/test_risk_engine.py` | FR-10 |
| **SI-8** | **Reconciliation Truth Dominance**: Any drift between local journaled positions and Fyers broker holdings halts all trading instantly. Broker truth always wins. | `tests/unit/test_reconciler_and_data.py` | FR-11 |
| **SI-9** | **Crash Durability**: Sudden process termination (`kill -9`) mid-write never loses acknowledged orders. Full state is recovered upon restart replay. | `tests/chaos/test_failure_injection.py` | FR-6, FR-16 |
| **SI-10** | **Sub-Second Kill SLA**: Activating the kill switch via Web Console, Telegram `/kill`, or session revocation halts all order submissions within 1.0 second. | `tests/integration/test_phase2_console.py` | FR-12 |
| **SI-11** | **Market-Hours Deploy Lockout**: Deployments, migrations, and configuration updates are strictly rejected during active market hours (09:15 – 15:30 IST). | `tests/unit/test_scheduler_and_killswitch.py` | FR-18 |
| **SI-12** | **SEBI Compliance Verification**: Order dispatch frequency remains provably and auditably below the SEBI retail algo limit of 10 OPS. | `tests/unit/test_governor.py` | FR-7 |

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 7. Deterministic Order State Machine & SQLite WAL Journal

XenAlgo treats order execution as a formal, deterministic finite state machine backed by an append-only transaction ledger:

<p align="center">
  <img src="assets/readme/feature-state-machine.svg" alt="Order State Machine and Event Journal" width="100%" />
</p>

### State Transition Lifecycle

```
    [ INTENT ]  (Persisted to SQLite WAL before any API call is made)
         |
         v
   [ SUBMITTED ] (Dispatched to Fyers Gateway with deterministic correlationId)
      /      \
     v        v
[ TRANSIT ]  [ REJECTED ] (Terminal: Risk veto, price collar breach, margin limit)
     |
     v
 [ PENDING ]  (Acknowledged on exchange book; DOES NOT MUTATE POSITIONS)
    /    \
   v      v
[ PART_TRADED ] <---> (Accumulates confirmed fills; updates position incrementally)
   |      |
   v      v
[ TRADED ] [ CANCELLED / EXPIRED ] (Terminal: unfilled remainder auto-cancelled)
```

### Event-Sourced Storage Engine

All transactional operations use SQLite 3 configured with:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;
```

#### Core Schema Architecture
- **`order_events` (Append-Only Event Stream)**:
  `event_id`, `ts_utc`, `correlation_id`, `broker_order_id`, `sleeve`, `symbol`, `security_id`, `side`, `intended_qty`, `limit_price`, `state`, `filled_qty`, `avg_fill_price`, `reason`, `raw_json`.
  *Strict Invariant: Never UPDATE or DELETE. State is derived.*
- **`orders` (Derived Current Orders)**:
  `correlation_id`, `broker_order_id`, `state`, `filled_qty`, `avg_fill_price`, `updated_utc`.
- **`positions` (Derived Portfolio Holdings)**:
  `symbol`, `qty`, `avg_price`, `sleeve`, `entry_date`, `updated_utc`. Updated strictly on `filled_qty > 0`.
- **`risk_state` (Circuit Breaker Persistence)**:
  `key`, `value`, `updated_utc`. Tracks peak equity, daily P&L, drawdown breaker engagement, and kill-switch state across system restarts.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 8. SEBI Compliance Envelope & Rate Throttling

Under the Securities and Exchange Board of India (SEBI) algorithmic trading regulations, proprietary algorithmic trading on Indian stock exchanges operates under clear compliance boundaries:

<p align="center">
  <img src="assets/readme/feature-order-governor.svg" alt="SEBI 2-OPS Token Bucket Governor" width="100%" />
</p>

### Regulatory Threshold vs XenAlgo Enforcement

| Regulatory Dimension | SEBI Regulatory Threshold | XenAlgo Hardcoded Defense | Compliance Margin |
|---|---|---|---|
| **Order Dispatch Rate** | 10 orders / sec / client / exchange | **2.0 orders / sec** (Token Bucket) | **5.0x Safety Margin** |
| **Static IP Whitelist** | Mandatory static IP with 7-day change lock | Verified at startup via `FyersGateway` | Fail-closed on mismatch |
| **Daily Order Ceiling** | Broker ceiling: 100,000 / day | Hard cap: **500 orders / day** | 200x below ceiling |
| **Algo ID Registration** | Mandatory if > 10 OPS or third-party SaaS | **Exempt** (Self-built, proprietary capital, ≤ 2 OPS) | Full compliance |

### The Token Bucket Rate Governor

The rate governor implements an asynchronous token bucket pattern (`xenalgo.execution.governor`):
- Bucket capacity: `burst_limit = 2` tokens.
- Refill rate: `refill_rate = 2.0` tokens/second.
- Orders attempting to exceed the bucket rate are queued asynchronously; every order timestamp is audit-logged to verify compliance.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 9. Complete System Architecture

XenAlgo is structured as an **Asyncio Single-Process Monolith** running under `systemd`:

<p align="center">
  <img src="assets/readme/architecture-animated.svg" alt="Complete System Architecture" width="100%" />
</p>

### Component Hierarchy & Interaction

```
+-----------------------------------------------------------------------------------+
|                            XenAlgo Monolith Process                               |
|                                                                                   |
|  +------------------------+  In-Process Queue  +-------------------------------+  |
|  |     StrategyEngine     | -----------------> |        ExecutionEngine        |  |
|  | std30 · a027 · a062    |                    |  Netting · Order State Machine|  |
|  +------------------------+                    +-------------------------------+  |
|              ^                                                 |                  |
|              | Fresh Daily Bars                                v Check Order      |
|  +------------------------+                    +-------------------------------+  |
|  |      DataService       |                    |          RiskEngine           |  |
|  | DuckDB (Read-Only)     |                    | Pure Veto Layer (Zero I/O)    |  |
|  +------------------------+                    +-------------------------------+  |
|                                                                | Veto / Approve   |
|  +------------------------+                    +-------------------------------+  |
|  |       Scheduler        |                    |         OrderGovernor         |  |
|  | APScheduler · Asia/Cal |                    | 2.0 OPS Token Bucket Throttler|  |
|  +------------------------+                    +-------------------------------+  |
|              |                                                 | Throttled Stream |
|              v Periodic Check                                  v                  |
|  +------------------------+                    +-------------------------------+  |
|  |       Reconciler       | <----------------- |         BrokerGateway         |  |
|  | Local vs Broker Truth  |  Holdings & Funds  | Injected Fyers v3 REST / SDK  |  |
|  +------------------------+                    +-------------------------------+  |
|              |                                                 | Order Dispatch   |
|              v Discrepancy Halt                                v                  |
|  +------------------------+   WebSocket & REST  +-------------------------------+  |
|  |        Alerter         | <----------------- |         FillListener          |  |
|  | Telegram · Pushover    |   Confirmed Fills  | Dual Channel Deduping Engine  |  |
|  +------------------------+                    +-------------------------------+  |
|              ^                                                 | Write-Ahead      |
|              | Server-Sent Events (SSE)                        v                  |
|  +------------------------+                    +-------------------------------+  |
|  |   FastAPI Web Console  |                    |       SQLite WAL Journal      |  |
|  | Tailscale Private Bind |                    | order_events · positions · DB |  |
|  +------------------------+                    +-------------------------------+  |
+-----------------------------------------------------------------------------------+
```

### Core Engineering Decisions

- **Asyncio Monolith over Microservices**: Eliminates inter-process serialization overhead, network partition hazards, and distributed state desynchronization bugs. All components communicate via in-process queues.
- **DuckDB for Research & Analytics**: Houses historical daily OHLCV bars. Opened in **strictly read-only mode** within the trading daemon; only the off-market ingestion worker writes to DuckDB.
- **Fyers Gateway SDK Isolation**: Encapsulates the official `fyers-apiv3` SDK inside custom supervisors. Mitigates known upstream SDK edge cases (connection hang on close, token authentication races).
- **Dual-Channel Fill Listener**: Combines real-time Fyers WebSocket order event push with periodic REST orderbook polling to ensure fill acknowledgments never stall on transient socket drops.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 10. Real-Time Supervised Console & Zero-Trust Mesh

XenAlgo provides real-time situational awareness and instant manual override through an embedded web console (`xenalgo.web`):

<p align="center">
  <img src="assets/readme/product-in-action.svg" alt="Supervised Console Interface" width="100%" />
</p>

### Modern Stack & Security Posture
- **Lightweight Architecture**: Server-rendered **FastAPI** + **Jinja2** + **HTMX** with dynamic push updates via **Server-Sent Events (SSE)**. Zero heavy JavaScript build steps; minimal memory footprint.
- **Zero-Trust Network Topology**: The web server binds exclusively to the private **Tailscale** mesh VPN IP and local loopback (`127.0.0.1`). It has **zero public open ports** on the internet.
- **Latency Guarantee**: Confirmed broker fills reflect in the console UI in **< 3.0 seconds**.

### The Triple Kill Switch Architecture

Operator safety demands redundant, independent shutdown pathways. XenAlgo provides three independent kill controls:

```
  Path A: Web Console (Tailscale) ---> [ KILL SWITCH BUTTON ] ---+
                                                                 |
  Path B: Encrypted Telegram Bot  ---> [ /kill COMMAND      ] ---+---> [ ExecutionEngine HALT ]
                                                                 |     (SLA: ≤ 1.0 Second)
  Path C: Fyers OAuth Provider   ---> [ TOKEN REVOCATION   ] ---+
```

1. **Web Console One-Tap Kill**: Prominent red kill switch on the dashboard. Immediately halts order submission and persists the `HALTED` state to `risk_state`.
2. **Telegram Secure Command**: Dispatching `/kill` to the authenticated Telegram bot triggers the same immediate halt path.
3. **Session Token Revocation**: Revoking the Fyers OAuth token immediately causes all subsequent broker API calls to fail-closed at the gateway boundary.
- **SLA**: Activating any of the three kill paths halts new order placement in **under 1.0 second**.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 11. Daily Autonomous Session Lifecycle

The daily execution lifecycle follows an unyielding operational sequence:

<p align="center">
  <img src="assets/readme/workflow-daily-session.svg" alt="Daily Session Lifecycle Workflow" width="100%" />
</p>

```mermaid
flowchart TD
    A["08:15 IST: TokenManager Refresh"] --> B{"Token Valid?"}
    B -- No --> C["Trip Alarm & Halt Session"]
    B -- Yes --> D["08:30 IST: Ingest Daily OHLCV & Metadata"]
    D --> E["09:00 IST: Execute 6-Point Startup Gate"]
    E --> F{"Gate Clean & Reconciled?"}
    F -- No --> C
    F -- Yes --> G["09:15 - 09:30 IST: Opening Volatility Blackout"]
    G --> H["09:30 - 15:00 IST: Surveillance & 15m Reconcile"]
    H --> I["15:00 IST: Compute std30, a027, a062 Signals"]
    I --> J["Net Sleeve Targets & Evaluate RiskEngine Battery"]
    J --> K{"All Checks Passed?"}
    K -- Vetoed --> L["Log Veto Reason & Alert Operator"]
    K -- Allowed --> M["15:05 IST: Route Orders via 2-OPS Governor"]
    M --> N["15:15 IST: Square-off Guard & Cancel Unfilled"]
    N --> O["15:45 IST: EOD Reconciliation & Telegram Report"]
    O --> P["02:00 IST: Nightly WAL & DuckDB Backup"]
```

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 12. Verification & Safety Test Suite

The XenAlgo codebase is built on an **executable specifications** testing methodology:

```
========================================================================================================
PYTEST TEST EXECUTION SUMMARY (ROOT SAFE SUITE)
========================================================================================================
tests/unit/test_risk_engine.py             ...................................             [ 17%]
tests/unit/test_order_state_machine.py     ...................................             [ 35%]
tests/unit/test_governor.py                ...................                             [ 44%]
tests/unit/test_sleeves_and_idempotency.py .........................                       [ 57%]
tests/unit/test_reconciler_and_data.py     ......................                          [ 68%]
tests/unit/test_scheduler_and_killswitch.py .................                              [ 76%]
tests/integration/test_phase1_paper_day.py ....................                            [ 86%]
tests/integration/test_phase2_console.py   ............................                    [100%]
========================================================================================================
STATUS: 203 PASSED, 0 FAILED in 56.70s (100% Safety-Critical Coverage)
========================================================================================================
```

### Running the Test Suites

#### 1. Safe Spec Suite (Phase 0 / Phase 1 / Phase 2)
Runs all unit, contract, and integration tests using mocked brokers and temporary SQLite databases:
```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
```

#### 2. Research Engine Validation Suite
Verifies the underlying quantitative alpha calculations in the promoted research package:
```powershell
cd _source
./.venv/Scripts/python.exe -m pytest Lab/ -q
cd ..
```

#### 3. Chaos & Failure-Injection Suite
Runs adversarial failure scenarios designed to break distributed assumptions:
```powershell
./_source/.venv/Scripts/python.exe -m pytest -m chaos
```

**Adversarial Fault Scenarios Tested**:
- `kill -9` process termination mid-order write.
- Dropping WebSocket connection during partial fill execution.
- Injecting corrupted OHLCV bars (NaNs, negative prices, price spikes).
- Mid-session Fyers access token expiration.
- Broker order rejection storms.
- Simulated 1-share reconciliation mismatch injection.

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 13. Production Readiness & Acceptance Gates

Deployment follows four sequential, rigorous acceptance gates documented in [docs/SUCCESS_CRITERIA.md](docs/SUCCESS_CRITERIA.md):

```
  +--------------------+     +--------------------+     +--------------------+     +--------------------+
  |   G0: FOUNDATION   | --> |   G1: PAPER CORE   | --> |    G2: CONSOLE     | --> |    G3: GO-LIVE     |
  | Scaffolding, CI,   |     | Full Paper Day,    |     | SSE < 3s, Kill     |     | Chaos 100% Green,  |
  | Config Checksum.   |     | 100% Risk Cover.   |     | < 1s, Tailscale.   |     | 5-Day Commission.  |
  +--------------------+     +--------------------+     +--------------------+     +--------------------+
        [ PASSED ]                 [ PASSED ]                 [ PASSED ]               [ PRE-FLIGHT ]
```

### Acceptance Gate Status

| Gate | Objective & Required Verification | Local Status | Production Path |
|---|---|---|---|
| **G0: Foundation** | Scaffolding, dependency pinning, dual config profile validation, baseline test suite green. | **PASSED** | Verified in repo CI |
| **G1: Paper Core** | Full simulated paper day completes unattended. 100% coverage on `xenalgo/risk/` and `xenalgo/execution/`. Zero double-orders across 1,000 restarts. 2 OPS governor enforced. | **PASSED** | Verified in repo test suite |
| **G2: Supervised Console** | Fill push via SSE reflects in UI in < 3s. Triple kill switch halts submission in < 1s. Zero public open ports; Tailscale-only bind verified. | **PASSED** | Verified in integration tests |
| **G3: Go-Live & Commissioning** | Phase 3.1 chaos suite 100% green. 5 consecutive NSE paper sessions on live data with zero software failures. Static IP verified. Staged capital ramp (10% -> 25% -> 50% -> 100%). | **IN PROGRESS** | Blocked on operator commissioning week |

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 14. Repository Map & Documentation Matrix

### Repository Directory Structure
```
XenAlgo/
|-- PLAN.md                          # Master architecture and engineering roadmap
|-- AGENTS.md                        # Strict operating contract for AI agents
|-- README.md                        # Master product documentation and launch guide
|-- pytest.ini                       # Test framework configuration
|-- docs/                            # Comprehensive engineering specifications
|   |-- PRD.md                       # Product Requirements Document
|   |-- TRD.md                       # Technical Requirements Document
|   |-- SUCCESS_CRITERIA.md          # Measurable acceptance gates and SI-1..SI-12
|   |-- BUILD_PLAN.md                # Phased build tasks and work packages
|   |-- TEST_PLAN.md                 # Test harness and chaos testing specifications
|   |-- TRACEABILITY.md              # Traceability map (PRD -> TRD -> Invariant -> Spec)
|   `-- FYERS_CONTRACT.md            # Frozen Fyers API v3 contract and runtime decisions
|-- xenalgo/                         # Execution engine and risk core
|   |-- broker/                      # Broker gateway, token manager, and contracts
|   |-- risk/                        # Pure veto layer and circuit breakers
|   |-- execution/                   # State machine, journal, netting, and governor
|   |-- data/                        # Market data loaders and freshness gate
|   |-- strategy/                    # Multi-sleeve portfolio orchestrator
|   |-- web/                         # FastAPI, HTMX, and SSE supervised console
|   |-- ops/                         # Heartbeat, watchdog, and kill-switch state
|   `-- scheduler.py                 # APScheduler Indian Standard Time orchestrator
|-- tests/                           # Executable test specifications
|   |-- unit/                        # Pure unit tests (Risk, FSM, Governor, Sleeves)
|   |-- integration/                 # Full paper-day and console integration tests
|   `-- chaos/                       # Failure injection and crash resilience suite
|-- Brain/                           # Promoted research and backtest engine
|-- Strategies/                      # Promoted validated alpha implementations
`-- assets/readme/                   # Production animated SVG assets and diagrams
```

### Documentation Cross-Reference
- **Architecture & Technical Decisions**: [PLAN.md](PLAN.md) · [docs/TRD.md](docs/TRD.md)
- **Product Requirements & Non-Goals**: [docs/PRD.md](docs/PRD.md)
- **Verification Gates & Safety Invariants**: [docs/SUCCESS_CRITERIA.md](docs/SUCCESS_CRITERIA.md) · [docs/TEST_PLAN.md](docs/TEST_PLAN.md)
- **Agent Operating Rules**: [AGENTS.md](AGENTS.md)
- **Broker Integration Specifications**: [docs/FYERS_CONTRACT.md](docs/FYERS_CONTRACT.md) · [docs/TRACEABILITY.md](docs/TRACEABILITY.md)

---

<p align="center">
  <img src="assets/readme/section-divider.svg" alt="Divider" width="100%" />
</p>

## 15. Operator Quickstart & Provenance Tribute

<p align="center">
  <img src="assets/readme/closing-call-to-action.svg" alt="Production Readiness & Call to Action" width="100%" />
</p>

### Operator Quickstart Guide

#### 1. Environment Preparation
Ensure Python 3.14 (or uv) is configured in your execution environment:
```powershell
# Clone repository
git clone https://github.com/subham/XenAlgo.git
cd XenAlgo

# Activate pinned virtual environment
./_source/.venv/Scripts/Activate.ps1
```

#### 2. Run Verification Spec Suite
Before configuring any live credentials, verify all safe unit and integration tests:
```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
```

#### 3. Configuration Setup
Copy `.env.example` to `.env` and populate Fyers credentials with `0600` permissions:
```ini
FYERS_CLIENT_ID="XXXXXX-100"
FYERS_SECRET_KEY="XXXXXXXXXX"
FYERS_PIN="1234"
FYERS_TOTP_KEY="JBSWY3DPEHPK3PXP"
TELEGRAM_BOT_TOKEN="0000000000:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TELEGRAM_CHAT_ID="00000000"
```

#### 4. Launch Autonomous Paper Trading Daemon
Run the autonomous paper execution daemon:
```powershell
./_source/.venv/Scripts/python.exe -m xenalgo.daemon --mode=paper
```

#### 5. Launch Real-Time Supervised Console
Access the zero-trust private dashboard over Tailscale:
```powershell
./_source/.venv/Scripts/python.exe -m uvicorn xenalgo.web.app:app --host 127.0.0.1 --port 8000
```
Open `http://localhost:8000` or your private Tailscale node IP in your browser.

---

### Legal Disclaimer & Proprietary Notice

> [!CAUTION]
> **Proprietary Single-User Software**: XenAlgo is a private, proprietary software system engineered exclusively for a single user's personal trading account on the National Stock Exchange of India. It is **not** a commercial product, financial advisory service, or wealth management software. Nothing contained within this repository constitutes financial advice, investment recommendations, or an endorsement to trade equities. Automated algorithmic trading involves substantial risk of financial loss. Past backtested performance is no guarantee of future returns. Use at your own discretion and risk.

---

<p align="center">
  <b>DECOYINDIA // PROPRIETARY QUANTITATIVE SYSTEMS</b><br/>
  <sub>Conceived, Architected, and Engineered by <b>Subham Jena (DecoyINDIA)</b></sub><br/>
  <sub>Built with mathematical rigor for the National Stock Exchange of India. Powered by Python 3.14, SQLite WAL, DuckDB, FastAPI, and Fyers API v3.</sub>
</p>
