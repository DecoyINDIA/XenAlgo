# XenAlgo — Technical Requirements Document (TRD)

**Version:** 1.0 · **Date:** 2026-07-04 · **Companion to:** `PRD.md`, `PLAN.md`

---

## 1. System Overview

Single-process Python **asyncio monolith** (`xenalgo` service), one systemd unit. Reuses the existing research/backtest engine (`Brain/`) and strategies (`Strategies/`); adds a new live-execution package (`xenalgo/`). DuckDB for market data (read-mostly), SQLite (WAL) for transactional state. Dashboard served in-process (FastAPI). Broker connectivity via a Fyers-backed gateway with a broker-agnostic interface.

**Runtime:** CPython 3.12/3.13 (standard build; free-threading not used). Prod pins Python and every dependency to exact versions.

---

## 2. Component Specification

### 2.1 BrokerGateway (`xenalgo/broker/`)
Abstract `BrokerInterface` + `FyersGateway` implementation. All Fyers I/O funnels here.
- **Transport:** `httpx.AsyncClient` for REST; SDK/`websockets` for streams.
- **Rate limiting:** per-API-class token buckets — orders ≤2/s (self-imposed, well under Fyers' 10/s and SEBI's 10/s), non-trading/data calls queued under broker limits. Buckets are the single choke point; strategy code cannot bypass them.
- **Idempotency:** every order sends a deterministic `correlationId` as the Fyers order `tag`. Pre-submit, the gateway checks cached/orderbook rows for that tag; if an order exists, it adopts that order instead of re-submitting.
- **Order type:** marketable LIMIT (LTP ± collar), `productType=CNC`, `validity=DAY`. Raw MARKET is disallowed by policy.
- **Retries:** idempotent GETs retried with exponential backoff + jitter; POSTs never blind-retried — on ambiguous failure, gateway reconciles via correlationId before any resend.
- **Error mapping:** DH-905 (invalid IP / bad fields) and DH-906 (account not enabled) surfaced as typed exceptions; DH-905/invalid-IP triggers a startup-gate failure, not a silent retry loop.
- **SDK containment:** WebSocket clients (`MarketFeed`, `OrderUpdate`) run under an external supervisor task with a hard timeout on `close_connection()` (SDK bug #139) and force-kill+reconnect on hang/auth-race (#75/#65). Exact SDK version pinned.

### 2.2 TokenManager (`xenalgo/broker/token.py`)
- Refresh via the Fyers OAuth2 auth-code/token flow, scheduled 08:15 IST.
- Persists token + expiry to a dedicated token SQLite file outside backup scope; POSIX hosts chmod it to `0600`.
- Exposes `ensure_valid()` used by the startup gate; failure → `TradingBlocked` for the session + critical alert.

### 2.3 DataService (`xenalgo/data/`)
- Wraps existing `DataManager`/`load_panel`; DuckDB opened **read-only** in the live process (single-writer discipline; the nightly ingest task is the only writer).
- **Freshness gate:** `assert_panel_fresh(panel, expected_trading_date)` — latest bar must equal the expected NSE trading date per calendar; else raise `StaleDataError`.
- **Price sanity:** per-symbol bounds check (no NaN, >0, day-over-day move within ±collar-band) before a price is usable for sizing or limit pricing.

### 2.4 StrategyEngine (`xenalgo/strategy/`)
- Discovers the three alphas via existing `AlphaEngine`.
- Runs each as a **sleeve** with fixed capital fraction (config; default ⅓). Each sleeve calls the existing `PortfolioEngine` scoped to its own capital and produces target weights → target shares.
- Emits `TargetPortfolio` per sleeve (symbol → target qty) with sleeve attribution tag.

### 2.5 RiskEngine (`xenalgo/risk/`) — independent veto layer
- Pure, side-effect-free `check(order, context) -> Decision(allow|reject|scale, reason)`; **no strategy code can bypass it** — ExecutionEngine calls it on every order.
- **Layer 1 pre-trade checks:** max notional, ADV liquidity cap (≤5% 20-day ADV), price collar (±3% of prev close), per-symbol ≤10% portfolio, max positions (per-sleeve + global), cash sufficiency w/ fee buffer, duplicate (correlationId), restricted-list (ASM/GSM/circuit/blacklist), symbol/security-id sanity.
- **Layer 2 breakers (stateful, in `risk_state` table):** daily-loss halt, drawdown halt (manual re-arm), consecutive-failure halt, stale-data breaker, reconciliation-mismatch breaker. Breaker state persists across restart.
- Limits are config-driven and versioned; loaded at startup with checksum.

### 2.6 ExecutionEngine (`xenalgo/execution/`)
- Consumes `TargetPortfolio`(s), nets across sleeves, computes deltas vs reconciled positions, orders **SELL-before-BUY** (cash-safety, matches backtest).
- **Order state machine** persisted to `order_events` (write-ahead intent → submit → terminal). States: `INTENT, SUBMITTED, TRANSIT, PENDING, PART_TRADED, TRADED, REJECTED, CANCELLED, EXPIRED`.
- Enforces **minimum holding period** (swing; can't churn) and per-window order timeout (auto-cancel unfilled at window end).
- Never assumes fills — waits for FillListener confirmation to advance state and mutate positions.

### 2.7 FillListener (`xenalgo/execution/fills.py`)
- Primary: Fyers Order WebSocket. Redundant: REST orderbook poll for orders stuck in non-terminal state past a timeout. There is no public HTTP postback route.
- Deduplicates by `orderId`+status; idempotent application to the journal (applying the same fill twice is a no-op).

### 2.8 Reconciler (`xenalgo/execution/reconcile.py`)
- Merges `get_holdings()` (CNC/delivery — where swing positions actually live) **and** `get_positions()` (intraday) into broker-truth positions.
- Portfolio value = fund-limit cash + Σ holdings×LTP.
- Runs at startup (blocks trading until clean), every 15 min in market hours, and post-execution. Mismatch beyond tolerance → reconciliation breaker → halt + alert. **Broker is always source of truth.**

### 2.9 Scheduler (`xenalgo/scheduler.py`)
- `APScheduler` `AsyncIOScheduler`, timezone `Asia/Kolkata`.
- Calendar = `pandas_market_calendars` (XNSE) **+** a maintained `nse_overrides.yaml` (muhurat/ad-hoc). Jobs: 08:15 token, 08:30 data sync + scrip-master + restricted-list refresh, 09:00 startup gate + reconcile, 15:00–15:20 execution (rebalance days), 15:15 square-off guard check, 15:45 EOD, 02:00 backups.
- Trading-window guards: block 09:15–09:30 and post-15:20.

### 2.10 Alerter (`xenalgo/alerts.py`)
- Telegram (primary, every order/fill/rejection/breaker/summary) with optional inline-button confirmations. Pushover (retry-until-ack) for system-health criticals. Email for weekly audit report. Non-blocking; alert failure never blocks trading logic but is itself logged.

### 2.11 Dashboard (`xenalgo/web/`)
- FastAPI + Jinja2/HTMX + SSE. Screens per PRD §C. Binds to Tailscale/loopback interface only. Kill-switch endpoint + breaker re-arm (authenticated action, token required). Read-only console endpoints are unauthenticated, which is an accepted risk mitigated by the Tailscale/loopback bind restriction. Read-only config view during market hours.

### 2.12 Watchdog / KillSwitch (`xenalgo/ops/`)
- systemd `Restart=on-failure`; external heartbeat to healthchecks.io each cycle; missed beat → Pushover page.
- KillSwitch state in SQLite; three setters (dashboard, Telegram `/kill`, broker Trader's-Control API); ExecutionEngine checks it before every submit (≤1s effect).

---

## 3. Data Model (SQLite, WAL, `synchronous=FULL`)

```sql
-- Append-only event log (never UPDATE/DELETE)
order_events(
  event_id INTEGER PRIMARY KEY,       -- autoincrement
  ts_utc TEXT NOT NULL,               -- ISO8601
  correlation_id TEXT NOT NULL,
  broker_order_id TEXT,               -- null until submitted
  sleeve TEXT NOT NULL,
  symbol TEXT NOT NULL,
  security_id TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  intended_qty INTEGER NOT NULL,
  limit_price REAL,
  state TEXT NOT NULL,                -- INTENT..EXPIRED
  filled_qty INTEGER DEFAULT 0,
  avg_fill_price REAL,
  reason TEXT,                        -- rejection/cancel reason
  raw_json TEXT                       -- broker payload snapshot
);

-- Derived current state (rebuilt from events; updated in same txn as the event insert)
orders(correlation_id TEXT PRIMARY KEY, broker_order_id TEXT, state TEXT,
       filled_qty INTEGER, avg_fill_price REAL, updated_utc TEXT);

positions(symbol TEXT PRIMARY KEY, qty INTEGER, avg_price REAL,
          sleeve TEXT, entry_date TEXT, updated_utc TEXT);

portfolio_snapshots(ts_utc TEXT PRIMARY KEY, equity REAL, cash REAL,
                    positions_value REAL, day_pnl REAL, peak_equity REAL);

risk_state(key TEXT PRIMARY KEY, value TEXT, updated_utc TEXT);
          -- e.g. daily_loss_halt, drawdown_halt, kill_switch, consecutive_failures

restricted_list(symbol TEXT PRIMARY KEY, reason TEXT, source TEXT, as_of TEXT);

config_versions(checksum TEXT PRIMARY KEY, applied_utc TEXT, yaml_snapshot TEXT);

audit_log(ts_utc TEXT, actor TEXT, action TEXT, detail TEXT);
```

- **Durability:** `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;` for the journal DB. Paper and live use separate physical DB files.
- **Invariant:** `positions`/`orders` are *derivable* by replaying `order_events`; a startup self-check replays and asserts equality with the stored derived tables.

---

## 4. Key Interfaces (contract sketches)

```python
class BrokerInterface(Protocol):
    async def place_order(self, req: OrderRequest) -> OrderAck: ...
    async def cancel_order(self, broker_order_id: str) -> OrderAck: ...
    async def get_order_by_correlation(self, cid: str) -> Optional[OrderStatus]: ...
    async def get_holdings(self) -> list[Holding]: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_funds(self) -> Funds: ...

@dataclass(frozen=True)
class OrderRequest:
    correlation_id: str; sleeve: str; symbol: str; security_id: str
    side: Literal["BUY","SELL"]; qty: int; limit_price: float

class RiskDecision(Enum): ALLOW=auto(); REJECT=auto(); SCALE=auto()

class RiskEngine:
    def check(self, order: OrderRequest, ctx: RiskContext) -> tuple[RiskDecision, int, str]:
        """Returns (decision, allowed_qty, reason). Pure; no I/O."""
```

---

## 5. Configuration (additions to `config.yaml`)
```yaml
sleeves:
  std30:    { capital_fraction: 0.34, enabled: true }
  alpha_027:{ capital_fraction: 0.33, enabled: true }
  alpha_062:{ capital_fraction: 0.33, enabled: true }

risk:
  max_order_notional_inr: 200000
  max_pct_of_adv: 0.05
  price_collar_pct: 0.03
  max_position_pct: 0.10
  max_positions_global: 40
  daily_loss_halt_pct: 0.02
  drawdown_halt_pct: 0.10
  consecutive_failure_halt: 3

execution:
  order_type: "MARKETABLE_LIMIT"
  buy_collar_pct: 0.005
  window_start: "15:00"
  window_end: "15:20"
  order_timeout_min: 10

governor:
  max_orders_per_sec: 2
  max_orders_per_day: 500

broker:
  fyers_sdk_version: "external-injected"   # SDK/REST client injected at the live boundary
  static_ip_primary: "x.x.x.x"
  static_ip_secondary: "y.y.y.y"
```

---

## 6. Security & Ops
- Secrets (`client_id`, `PIN`, TOTP secret, Telegram/Pushover tokens) in `.env` (0600, gitignored, excluded from backups). Access tokens are ephemeral (not backed up).
- Dashboard on loopback or Tailscale interface only; zero public postback ports.
- Startup gate (all must pass or refuse to trade): valid token · static IP verified · calendar/scrip-master current · reconciliation clean · config checksum matches · journal replay self-check passes.
- No deploy during market hours (enforced in deploy script). Nightly `.backup` + DuckDB→Parquet → off-box; monthly restore drill.
- **Hosting remains zero-cost** (PLAN.md §6): Oracle Cloud Always Free is the permanent paper/live host; the current VM is Oracle Linux 9 on `VM.Standard.E2.1.Micro` with isolated paper/parity/live SQLite/DuckDB paths. Docker keeps recovery reproducible. Preserve and verify the Oracle network identity required by the active broker app before activation. Host loss fails closed and requires a reviewed recovery; it never triggers an automatic infrastructure move.

## 7. Technology Choices (locked)
DuckDB (market data, read-only in live) · SQLite WAL/FULL (state) · asyncio monolith · httpx · APScheduler · pandas_market_calendars(XNSE)+overrides · FastAPI+HTMX+SSE · Tailscale · systemd · Telegram+Pushover · **Oracle Cloud Always Free (dev/paper) → AWS ap-south-1 or DO Bangalore (live)**. Broker: **Fyers** via injected SDK/REST client; current `fyers-apiv3` releases are kept out of CI until their Python 3.14 dependency chain is installable. Rationale in `PLAN.md` §3–§6.

## 8. Traceability
Each TRD component maps to PRD FRs: BrokerGateway→FR-7, TokenManager→FR-1, DataService→FR-3/FR-4, StrategyEngine→FR-4/FR-5, RiskEngine→FR-9/FR-10/FR-19, ExecutionEngine→FR-6, FillListener→FR-8, Reconciler→FR-11, Scheduler→FR-2, Alerter→FR-14, Dashboard→FR-15, Journal→FR-16, KillSwitch→FR-12, Paper mode→FR-13.

The authoritative executable mapping is maintained in `docs/TRACEABILITY.md`. Broker-neutral
interfaces are frozen in `xenalgo/broker/contracts.py`; Fyers-specific payloads remain inside
the injected adapters described in `docs/FYERS_CONTRACT.md`.
