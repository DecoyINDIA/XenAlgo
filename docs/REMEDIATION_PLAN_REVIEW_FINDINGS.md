# XenAlgo Remediation Plan — End-to-End Review Findings

**Purpose:** This is an executable implementation plan for an autonomous coding agent
(e.g. Antigravity) to fix every finding from the 2026-07-15 end-to-end project review.
It is self-contained: an agent should be able to complete it from this file plus the
repository, without the review conversation.

**Author of findings:** project-review audit, 2026-07-15.
**Ground truth at plan time:** `172 passed` (root suite), CI coverage gates green. The
green suite hides these bugs because test fixtures supply state that production omits
(LTP maps, shared broker instances). Every fix below therefore ships **with a test that
fails before the fix and passes after**.

---

## 0. Non-negotiable guardrails (read before touching code)

These come from `AGENTS.md` and the config validators. Violating any one fails the
review regardless of what else works:

1. **Never enable live trading.** `live_trading.enabled` stays `false`,
   `broker.order_api_enabled` stays `false`. No code path may call a real Fyers order API.
   Tests use `PaperBroker`/`MockBroker` only.
2. **RiskEngine stays a pure veto layer.** No I/O, no input mutation in `RiskEngine.check`.
   There is a test asserting purity — keep it green.
3. **Positions change only from confirmed fills.** Never mutate positions on
   `PENDING`/`SUBMITTED`/`ACCEPTED`.
4. **`order_events` is append-only.** Never `UPDATE`/`DELETE` it. State is derived by replay.
5. **Governor never exceeds 2 orders/sec.** Do not weaken `OrderGovernor` or its validator.
6. **Do not modify the three strategies** (`std30`, `alpha_027`, `alpha_062`) or the
   `Brain/` research math. Wiring them in (Task 3) means *calling* them, not editing them.
7. **No secrets in code, tests, logs, or commits.**
8. Every safety-invariant test (SI-1..SI-12) must stay green. If a change trips a safety
   test, the change is wrong — not the test.

**Verification commands (run after every task):**
```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
./_source/.venv/Scripts/python.exe -m pytest -m chaos
```
Full gate (must stay green before declaring done):
```powershell
python -m pytest -q --cov=xenalgo --cov-fail-under=90
python -m coverage run -m pytest tests/unit/test_risk_engine.py tests/unit/test_order_state_machine.py tests/unit/test_execution_phase_a.py tests/unit/test_reconciler_and_data.py tests/integration/test_phase1_paper_day.py tests/chaos/test_failure_injection.py && python -m coverage report --include="xenalgo/risk.py,xenalgo/execution/*" --fail-under=100
```

**Working rule:** one task = one focused commit (or PR). Each task lists the test to add
first. Write the test, watch it fail, implement, watch it pass. Do not batch unrelated tasks.

---

## Execution order (dependencies)

```
Task 1 (fill pricing) ─┐
Task 2 (paper state)  ─┼─ ship together; add process-restart test that covers both
Task 7 (recon dir)    ─┘   (Task 7 is the tripwire that should have caught Task 2)
        │
        ▼
Task 3 (strategy→execution bridge)   ← the actual missing product; largest task
        │
        ▼
Task 4 (data-sanity threshold)  ┐
Task 5 (holiday overrides)      ┴─ small; remove near-daily false halts pre-commissioning
        │
        ▼
Task 6 (atomic fill apply)
Task 8 (re-arm execution halt)
Task 9 (risk-veto vs halt policy decision)
        │
        ▼
Tasks 10–14 (mediums)  →  Task 15 (AGENTS.md + low/hygiene sweep)
```

---

## CRITICAL

### Task 1 — Paper fills must execute at a real price, never 0.0

**Severity:** Critical. **Files:** `xenalgo/paper_daemon.py`, `xenalgo/broker/paper.py`.

**Root cause:** `build_paper_dependencies` (`paper_daemon.py:434`) constructs
`PaperBroker()` with an empty `ltp` map. No production path ever populates `broker.ltp`
(grep confirms only tests pass `ltp=`). `PaperBroker.mark_filled` (`paper.py:92`) then does
`price = float(self.ltp.get(order["symbol"], order.get("avg_price") or 0.0))` → every fill
books at ₹0. Consequences: paper cash never moves, `avg_fill_price` journals as 0.0, sleeve
slippage/return analytics are meaningless, and commissioning evidence records "clean"
sessions with fictional P&L.

**Fix:**
1. In `ProductionPaperDaemon.startup` (`paper_daemon.py`, where `self._previous_close` is
   built from `panel["close"]`), push those latest closes into the broker:
   `self.deps.broker.ltp.update(self._previous_close)`. This makes fills price at the
   last known close for the session. (If a later task introduces intraday marks, prefer
   those; close is the correct paper default today.)
2. Harden `PaperBroker.mark_filled` to **fail closed** instead of defaulting to 0.0: if no
   price is resolvable for the symbol, set the order state to `REJECTED` with reason
   `"no paper mark price"` and return without mutating holdings/cash. A silent ₹0 fill is
   worse than a rejected one.
3. Mirror the same LTP seeding in `PaperDayRunner.run` (`xenalgo/monolith.py`) if that path
   is still used, so both compositions are consistent.

**Test to add** (`tests/integration/test_production_paper_daemon.py`):
- Build the daemon via a helper that uses `build_paper_dependencies`-style wiring (empty
  `ltp`), run one rebalance session with a BUY, and assert the journaled `avg_fill_price`
  for the fill equals the panel's latest close for that symbol (not 0.0), and that
  `broker.cash` decreased by `qty * close`.
- Add a unit test on `PaperBroker.mark_filled`: with no `ltp` entry and no `avg_price`,
  the order ends `REJECTED` and holdings are unchanged.

**Acceptance:** No production code path can produce a fill at price 0.0. New tests fail on
current `main`, pass after fix. Full suite + coverage gates green.

---

### Task 2 — Paper broker state must survive a process restart

**Severity:** Critical. **Files:** `xenalgo/paper_daemon.py` (`build_paper_dependencies`
and/or `ProductionPaperDaemon.__init__`), `xenalgo/broker/paper.py`.

**Root cause:** `PaperBroker` is in-memory. Day 1 buys 10 SBIN → persisted to the journal.
Day 2 starts a new process → fresh `PaperBroker` with empty `holdings`/`cash`, while journal
replay says +10 SBIN. Any SELL of the day-1 position is rejected ("insufficient paper
holdings"); three such rejections trip the persistent consecutive-failure halt; and the
post-session reconcile reports drift → `reconciliation_clean=false` on every session after
the first. Gate D3 ("five consecutive clean sessions") is therefore unreachable. The
existing restart-idempotency test reuses the *same* broker instance
(`test_production_paper_daemon.py:84`), so it never simulates a real restart.

**Fix:** Seed the paper broker from journal replay at construction. In
`build_paper_dependencies` (after the `Journal` is created, before returning deps):
1. Build `PositionBook.from_replay(journal)`.
2. For every symbol with nonzero replayed qty, set `broker.holdings[symbol] = qty`.
3. Reconstruct `broker.cash` deterministically: persist cash as part of paper state, OR
   derive it as `initial_cash - sum(signed_qty * avg_fill_price)` from the journal. Prefer
   **persisting** paper cash/holdings in a dedicated `paper_state` table in the same SQLite
   file (append-only journal stays untouched; this is separate mutable state), reloaded on
   startup. Document the choice in a `ponytail:`-style comment if you take the derived route.

Whichever route: after a restart, `broker.get_holdings()` must match journal replay, and a
SELL of a prior-day position must succeed.

**Test to add (the missing coverage):** a true process-restart simulation in
`tests/integration/test_production_paper_daemon.py`:
- Session day 1: BUY 10 SBIN via a fresh `build_paper_dependencies`-wired daemon against a
  `tmp_path` journal. Assert holdings.
- **Discard the daemon and broker entirely.** Re-run `build_paper_dependencies` against the
  *same journal path* (new `PaperBroker` instance) → new daemon.
- Session day 2: SELL 10 SBIN. Assert the SELL is accepted and fills, post-session
  `reconciliation_clean` is `True`, and the engine is not halted.

**Acceptance:** Five sequential sessions (buy then hold/sell across restarts) all report
`reconciliation_clean=True` and no spurious halt. New restart test fails on `main`, passes
after fix.

---

### Task 7 — Reconciliation must detect local-only drift (do this with Tasks 1–2)

**Severity:** High, but fix alongside Task 2 — it is the tripwire that should have caught it.
**Files:** `xenalgo/paper_daemon.py` (`startup` ~line 175, scheduled `reconciliation` job
~line 367).

**Root cause:** `local = {symbol: replay.qty(symbol) for symbol in self.deps.broker.holdings}`
iterates **broker** holdings keys only. When the journal has a position the broker doesn't
(exactly the restart scenario), `local == {} == truth` → falsely "clean". The drift the
startup gate most needs to catch is invisible to it.

**Fix:** Key `local` on the union of replayed symbols and broker symbols:
```python
replay = PositionBook.from_replay(self.deps.journal)
symbols = set(self.deps.broker.holdings) | {  # replayed symbols
    row_symbol for row_symbol in replay_symbols_with_nonzero_qty
}
local = {symbol: replay.qty(symbol) for symbol in symbols}
```
Apply the same fix to the `ScheduledPaperRuntime` `reconciliation` job. `Reconciler.reconcile`
already unions both sides correctly — only the `local` construction is wrong.

**Test to add:** with a journal holding +10 SBIN and a broker that returns no holdings
(pre-Task-2 state), `startup` must raise `StartupBlocked` (reconciliation check fails), not
pass. After Task 2 seeds the broker, the same scenario passes. Add both assertions.

**Acceptance:** Local-only drift is detected at startup and by the scheduled reconciliation
job. Test fails on `main`, passes after fix.

---

### Task 3 — Wire the strategy layer to execution (the missing product)

**Severity:** Critical. **Files:** new module `xenalgo/session_composition.py` (or similar),
`xenalgo/paper_daemon.py` (`main`), `deploy/oracle/xenalgo-paper.service`, plus
status/doc wording.

**Root cause:** Nothing under `xenalgo/` imports `Brain` or `Strategies`.
`ScheduledPaperRuntime` is only instantiated in tests. `paper_daemon.main()` deliberately
exits (`"scheduled daemon service requires an explicit runtime panel provider"`). The Oracle
systemd unit's `ExecStart` runs only the **web console** (`python -m xenalgo.web.server`),
with preflight as `ExecStartPre`. So the deployed host runs a dashboard + preflight but has
**no session runner** that turns strategy signals into `PaperOrderPlan`s. `docs/HANDOFF.md`
acknowledges this; README "Current Status" and the D2-complete ledger read as if the daemon
is running sessions.

**Fix (build the missing composition — paper-only, injected boundaries):**
1. **Panel provider:** `panel_provider(trading_date) -> dict` that loads the daily OHLCV
   panel via the existing `xenalgo.data.FyersHistoryLoader` / `host_preflight`-style fetch,
   validated by `validate_history_frame` and `assert_panel_fresh`. Network client is
   **injected**, so tests pass a fake and CI stays mock-only.
2. **Order provider:** `order_provider(trading_date, panel) -> Iterable[PaperOrderPlan]`
   that calls the existing strategies/`Brain` alpha+portfolio path to produce target
   weights → net deltas → `PaperOrderPlan`s. **Call, don't modify** `Brain`/`Strategies`.
   Reuse `xenalgo.strategy.SleeveAllocator` and `net_targets`. Each plan must carry a
   deterministic `correlation_id` (e.g. `f"{sleeve}:{symbol}:{trading_date}"`), preserving
   idempotency.
3. **Compose** these into `ScheduledPaperRuntime` and give `paper_daemon.main()` a real
   runnable path (behind an explicit flag so `--check` still works). Keep the
   `PaperDependencies.__post_init__` paper-only assertions intact.
4. **systemd:** add a `xenalgo-session` oneshot/timer unit (mirroring the existing
   preflight timer) that runs the session runner at the execution window (15:00 IST), or
   change the paper service to run the runtime. Do **not** run it during a live-order path.
   Keep the market-hours deploy guard.
5. **Status wording:** update README "Current Status" and `docs/DEPLOYMENT_STATUS.md` so the
   claim matches reality (paper daemon composition now exists and is deployable). Do not
   overclaim external deployment proof — D3/D4/D5 remain external-bound.

**Test to add** (`tests/integration/`): an end-to-end session using an injected fake panel
source and the real strategy→plan path, asserting that plans are generated, submitted
through `ExecutionEngine`, filled at real prices (Task 1), and journaled. No network, no
live API. Assert `live_order_api_calls == 0` semantics hold.

**Acceptance:** A single command (documented) runs a full paper session on injected data,
producing evidence with real fills and clean reconciliation. `Brain/` and `Strategies/`
unchanged (`git diff` shows no edits there). Status docs match capability.

> **Scope note for the agent:** this is the largest task. If splitting, land the
> composition + tests first (agent-verifiable), then the systemd/timer wiring, then the doc
> wording. Never wire anything that could reach a live order API.

---

## HIGH

### Task 4 — Separate the data-sanity threshold from the order collar

**Severity:** High. **Files:** `xenalgo/data.py` (`assert_latest_prices_sane`,
`price_is_sane`), `xenalgo/paper_daemon.py:162-164`, `config/config.live.yaml` (add key).

**Root cause:** `assert_latest_prices_sane` reuses `price_collar_pct` (3%, the *order
pricing* collar) as a *daily-move* sanity bound. NSE equities routinely move 3–20% in a day;
on a broad universe some symbol exceeds 3% most days → `CorruptDataError` → `StartupBlocked`
→ whole session lost on good data. Fail-closed, but it is a designed-in denial of operation.

**Fix:**
1. Add a distinct config key, e.g. `risk.data_sanity_move_pct: 0.25` (NSE circuit limits are
   typically ≤20%; 25% gives headroom), in `config.live.yaml`.
2. `assert_latest_prices_sane` takes a `sanity_move_pct` param (default ~0.25), separate
   from the order collar. Callers pass the new config value, not `price_collar_pct`.
3. Keep `price_collar_pct` (3%) for order pricing / `RiskEngine` only — do not change risk
   collar behavior.

**Test to add** (`tests/unit/test_reconciler_and_data.py` or data tests): a symbol that
moved 8% day-over-day passes data sanity (with 25% bound) but would still be collared at the
order layer. A symbol that moved 40% (or NaN/≤0) still raises `CorruptDataError`.

**Acceptance:** Realistic single-day moves no longer block startup; genuinely corrupt data
(NaN, ≤0, absurd jumps) still fails closed. Config validator still accepts the file.

---

### Task 5 — Load the NSE holiday overrides that are configured but ignored

**Severity:** High. **Files:** `xenalgo/paper_daemon.py` (`build_paper_dependencies`),
`xenalgo/host_preflight.py` (`latest_completed_trading_day` callers), `xenalgo/scheduler.py`
(`MarketCalendar` — may add a loader), `config/nse_overrides.yaml`.

**Root cause:** No code reads `nse_overrides.yaml` (grep: only config/docs/tests reference
it). `MarketCalendar()` defaults to "weekday = trading day" in both the daemon deps and the
preflight. On every weekday NSE holiday: the calendar check passes but panel freshness fails
→ false `StartupBlocked` alert; and the day *after* a holiday, `latest_completed_trading_day`
returns the holiday → preflight fails on good data.

**Fix:**
1. Add a loader (e.g. `MarketCalendar.from_overrides_file(path)` or a free function in
   `scheduler.py`) that reads `config/nse_overrides.yaml` into the `overrides: dict[date, str]`
   shape `MarketCalendar` already accepts.
2. In `build_paper_dependencies`, construct the calendar from
   `config.data["scheduler"]["overrides_file"]` (resolved against `root`) and put it on
   `PaperDependencies.calendar`.
3. In `host_preflight.main`, pass `deps.calendar` into `latest_completed_trading_day` (it
   already accepts a calendar param — it just isn't being given the loaded one).
4. Handle a missing/empty overrides file gracefully (empty overrides = weekday calendar),
   but log which path was loaded.

**Test to add** (`tests/unit/test_scheduler_and_killswitch.py` +
`tests/unit/`/integration for preflight): with an override marking a weekday as a holiday,
`is_trading_day` returns `False`, and `latest_completed_trading_day` skips the holiday to the
prior session. Verify `build_paper_dependencies` actually loads overrides from the config
path (use a `tmp` root with an overrides file).

**Acceptance:** Configured holidays are honored everywhere the calendar is used; no false
StartupBlocked on holidays or the day after. Existing scheduler tests stay green.

---

### Task 6 — Make fill application crash-atomic

**Severity:** High. **File:** `xenalgo/execution/__init__.py` (`PositionBook.apply_fill`,
~lines 285–308; `Journal.mark_applied`, `Journal.append`).

**Root cause:** `apply_fill` inserts into `applied_events` (its own commit inside
`mark_applied`) and *then* appends the fill to `order_events` (a separate commit inside
`append`). A crash between the two leaves the event marked applied but absent from the
journal — replay after restart silently drops the fill, violating the invariant "journal
replay matches derived state after crash recovery." Reconciliation would catch the resulting
drift later, but the invariant itself is broken.

**Fix:** Perform the dedup-mark and the journal append in **one SQLite transaction**. Options
(pick the cleaner one for this codebase):
- Add a `Journal` method that, within a single `_connect()` block, first does the
  `INSERT INTO applied_events` (relying on the PRIMARY KEY to raise `IntegrityError` on
  duplicates → treat as no-op) and, only if that insert succeeded, does the `order_events`
  + `orders` writes. Commit once. `PositionBook.apply_fill` calls this single method.
- Do not weaken the append-only guarantee: `order_events` is still insert-only.

Keep the in-memory `_cumulative_qty_by_order` / `_qty` updates ordered so they only apply
when the transaction commits (i.e., update memory after the atomic DB write succeeds, or
recompute from replay).

**Test to add** (`tests/chaos/test_failure_injection.py`): simulate a crash between the two
writes (e.g. monkeypatch `append` to raise after `mark_applied` in the *old* design to prove
the test catches it; then assert the new design leaves `applied_events` and `order_events`
consistent — either both present or both absent — and that replay reproduces the fill).

**Acceptance:** No interleaving of a crash can leave an event marked-applied-but-unjournaled.
Replay after simulated crash reproduces exact derived state. Existing dedup/idempotency
chaos tests stay green.

---

## MEDIUM

### Task 8 — Allow re-arming a tripped execution halt from the console

**Severity:** Medium. **Files:** `xenalgo/web/state.py` (`REARMABLE_BREAKERS`),
`xenalgo/execution/__init__.py` (`_load_halted`/`_record_*`).

**Root cause:** `REARMABLE_BREAKERS` includes `consecutive_failures` but not the persisted
`execution_halted` flag. Re-arming clears the counter while the halt flag keeps the engine
dead until someone hand-edits SQLite.

**Fix:** Add `execution_halted` to `REARMABLE_BREAKERS`. When an operator re-arms it via
`ConsoleStore.rearm`, clear the `execution_halted` key in `risk_state` (the DELETE already
does this generically) — confirm the `ExecutionEngine` re-reads `_load_halted()` on next
construction (it does, since state is loaded from the journal at init). Also clear
`consecutive_failures` together when re-arming the halt, so the engine doesn't immediately
re-trip. Audit-log the operator action (the existing `_audit` call covers this).

**Test to add** (`tests/integration/test_phase2_console.py`): trip the halt (3 rejections),
assert engine halted; operator re-arms `execution_halted`; a freshly constructed
`ExecutionEngine` against the same journal is no longer halted and accepts a valid order.

**Acceptance:** Operator can recover a halted engine entirely from the console/Telegram, with
an audit trail. No hand-editing of SQLite required.

---

### Task 9 — Decide deliberately whether risk vetoes count toward the permanent halt

**Severity:** Medium (policy decision + code). **File:** `xenalgo/execution/__init__.py`
(`submit`, the `RiskDecision.REJECT` branch ~line 393; `_record_failure`).

**Root cause:** A `RiskDecision.REJECT` (collar, no cash, position cap) calls
`_record_failure`, counting toward `consecutive_failure_halt`. Three ordinary risk vetoes in
one batch (very possible together with Task 4's false collars) persistently halt the engine.
Combined with Task 8's gap, the system could self-brick on normal vetoes.

**Decision required (pick one, document it in a comment + `docs/`):**
- **(Recommended)** Risk vetoes are *expected control outcomes*, not *failures*. Do **not**
  call `_record_failure` for `RiskDecision.REJECT`. Reserve the consecutive-failure breaker
  for **broker/submission failures and broker REJECTs** (genuine execution-path faults). This
  matches "prefer a missed trade over an unsafe trade" — a vetoed order is a *successful*
  safety outcome, not a fault.
- (Alternative) Keep counting them but raise the threshold and make it re-armable (Task 8).

Implement the recommended option unless the operator states otherwise: move
`_record_failure()` out of the risk-REJECT branch; keep it for the broker-exception and
broker-REJECTED branches.

**Test to add:** submitting N (> threshold) orders that all fail *risk* (e.g. price outside
collar) does **not** halt the engine; submitting N orders that the *broker* rejects **does**
halt it (existing `test_rejection_storm_trips_consecutive_failure_breaker` covers the broker
path — keep it green; add the risk-veto-does-not-halt counterpart).

**Acceptance:** Ordinary risk vetoes never brick the engine; genuine execution faults still
trip the breaker. Both tests green.

---

### Task 10 — Fix Fyers order-adoption state key mismatch

**Severity:** Medium. **Files:** `xenalgo/execution/__init__.py` (`submit`, ~line 378),
`xenalgo/broker/fyers.py` (`get_order_by_correlation` returns dict with `status`).

**Root cause:** `submit` reads `existing.get("state", "PENDING")` but `FyersGateway` stores
the field as `status`. An adopted Fyers order (even a REJECTED one) is reported as
"PENDING". Direction is safe (never resubmits), but wrong state propagates to journal
consumers. `MockBroker` uses `state`, so tests mask it.

**Fix:** Normalize in `submit`: read `existing.get("state") or existing.get("status") or
"PENDING"`. Alternatively, make `FyersGateway.get_order_by_correlation` return a dict that
includes a normalized `state` key. Prefer normalizing at the adapter boundary
(`fyers.py`) so `ExecutionEngine` stays broker-neutral.

**Test to add** (`tests/contract/test_fyers_operational_adapters.py`): adopt an existing
Fyers order that is REJECTED; assert `submit` returns `SubmissionResult.state == "REJECTED"`,
not "PENDING".

**Acceptance:** Adopted-order state is reported correctly for both Fyers and Mock brokers.

---

### Task 11 — Persist correlation-id dedup across restarts (defense in depth)

**Severity:** Medium. **Files:** `xenalgo/paper_daemon.py` (`_risk_context`),
`xenalgo/monolith.py` (`risk_context`), `xenalgo/execution/__init__.py` (`submit`).

**Root cause:** Both production compositions pass `seen_correlation_ids=set()` (always
empty), so RiskEngine's duplicate-correlation veto is inert; dedup rests entirely on
broker-side lookup, which the in-memory `PaperBroker` loses on restart. The Knight-Capital
chaos test passes only because `MockBroker` persists across simulated "restarts."

**Fix:** Populate `seen_correlation_ids` from the journal. `Journal.has_correlation` already
exists; add a cheap `Journal.known_correlation_ids()` (or reuse the `orders` table) and pass
the set into the `RiskContext`. Note this is defense-in-depth: `ExecutionEngine.submit`
already checks `broker.get_order_by_correlation` and `journal.has_correlation` before
placing — but with Task 2 seeding the broker from replay, and this making the risk-layer
veto real, dedup no longer depends on in-memory broker state.

**Test to add:** across a real process restart (reuse Task 2's harness), resubmitting a
already-journaled `correlation_id` is vetoed by RiskEngine (`"duplicate correlationId"`) even
with a fresh broker, and no second broker order is placed.

**Acceptance:** Duplicate correlation IDs are rejected after a restart by the risk layer, not
only the broker. Knight-Capital chaos test still green and now meaningful.

---

### Task 12 — Recover partial fills via the REST fallback channel

**Severity:** Medium. **Files:** `xenalgo/execution/__init__.py`
(`FillListener.poll_stuck_orders`, ~line 474), `xenalgo/broker/fyers.py`
(`fyers_payload_to_fill` price fallback).

**Root cause:** `poll_stuck_orders` skips anything whose state is not exactly `TRADED`, so a
`PART_TRADED` order stuck after a WebSocket drop is never recovered via REST. Separately,
`fyers_payload_to_fill` can emit `avg_price=0.0` from its fallback chain (`fyers.py:253-259`).

**Fix:**
1. In `poll_stuck_orders`, recover `PART_TRADED` as well as `TRADED`, emitting a `Fill` with
   the cumulative filled qty and an `event_key` that encodes state + cumulative qty (the
   `PositionBook` cumulative-delta logic already handles idempotent partial application).
2. In `fyers_payload_to_fill`, if no positive price is resolvable, do not emit a fill priced
   at 0.0 — either skip and let a later poll with price recover it, or carry a sentinel that
   the caller treats as "price unknown, do not book P&L at 0."

**Test to add** (`tests/chaos/test_failure_injection.py`): a WebSocket drop leaves a
`PART_TRADED` order at the broker; REST `poll_stuck_orders` recovers the partial fill into the
`PositionBook` with correct qty; a subsequent full fill applies the remaining delta exactly
once.

**Acceptance:** Partial fills survive a primary-channel loss; no fill is ever booked at ₹0
via the recovery path.

---

### Task 13 — Add a SELL-side veto to RiskEngine

**Severity:** Medium. **File:** `xenalgo/risk.py` (`check`, the `if order.side.upper() ==
"BUY"` blocks).

**Root cause:** Position caps, cash, and notional guard BUYs only. An oversized SELL
(oversell → unintended short / intraday position on the live broker) passes the "veto layer"
and relies on the broker to reject. The layer that is supposed to be the last line of defense
has a hole on the SELL side.

**Fix:** In `RiskEngine.check`, for `side == "SELL"`, cap the sellable quantity at the
current long position for that symbol (`ctx.positions[symbol]["qty"]`, floored at 0). If the
requested qty exceeds holdings, `SCALE` down to holdings (or `REJECT` if holdings ≤ 0 and the
system does not intend shorting — this is a single-account swing system that holds long
equity, so **reject oversell** is the correct default). Keep `check` pure (no I/O, no input
mutation) — read from `ctx`, return a new decision.

**Test to add** (`tests/unit/test_risk_engine.py`): SELL of 100 when holdings are 10 →
`SCALE` to 10 (or `REJECT` per chosen policy); SELL with zero holdings → `REJECT`
(`"no position to sell"`); a valid SELL within holdings → `ALLOW`. Assert the purity test
still holds.

**Acceptance:** The risk layer vetoes oversells server-side, not just the broker. Purity
test green. Document the short-selling stance in the test docstring with the SI/FR id.

---

### Task 14 — Authenticate the Telegram command sender before wiring a live bot

**Severity:** Medium (guard now; blocker before any live bot wiring). **File:**
`xenalgo/web/telegram.py` (`TelegramCommandRouter`).

**Root cause:** `TelegramCommandRouter.handle` trusts any input; there is no sender check.
Wired to a real bot, anyone who can message it could `/kill` or `/rearm kill_switch`. It is
currently a test-only handler, which is why this is Medium — but it must not reach a live bot
as-is.

**Fix:** Add an allowlist: the router (or its caller) verifies the incoming Telegram
`chat_id`/`user_id` against `TELEGRAM_CHAT_ID` (already an env var) before executing any
state-changing command (`/kill`, `/rearm`). Read-only commands (`/status`, `/positions`) may
stay open or also be gated — gate them too for consistency. The allowlist value comes from
env/config, never hardcoded.

**Test to add** (`tests/integration/test_phase2_console.py`): a command from a non-allowlisted
sender is refused with an explanatory message and performs no state change; the same command
from the allowlisted operator succeeds.

**Acceptance:** State-changing Telegram commands require an allowlisted sender. No live bot
wiring is added in this task — only the guard.

---

## LOW / HYGIENE (Task 15 — sweep in one commit)

Each is one-line-to-small. Do them together; add/adjust tests only where behavior changes.

1. **`AGENTS.md` says Dhan throughout; the code is Fyers.** Update the operating contract:
   broker name (Dhan→Fyers), SDK pin note (`dhanhq==2.0.2` → the Fyers external-injected
   boundary described in `config.py`), and the stale "not currently a git repo" line (it is a
   git repo on `main`). This file is what every future agent reads first — stale safety
   directives are a real hazard. **Do not** change the safety invariants themselves, only the
   broker-identity facts.
2. **`.env.example` missing `XENALGO_CONSOLE_TOKEN`**, which `web/server.py:41-43` hard-requires
   to start the console. Add it with an empty value and a comment.
3. **`OrderGovernor._used_today` never resets** — a long-lived process starves at 500
   cumulative orders. Add a per-trading-day reset (reset when the IST trading date rolls over;
   inject the clock/date so it stays testable). Keep the ≤2/sec cap untouched. Add a test that
   crossing a day boundary restores `remaining_today()`.
4. **Console `active_breakers` counts the `consecutive_failures` counter row** as a breaker,
   inflating the number. Exclude non-breaker bookkeeping keys from the count in
   `ConsoleStore.snapshot` summary.
5. **`orders` upsert applies `state=excluded.state` unconditionally** (`Journal.append`) — an
   out-of-order late event can regress derived order state. Guard the state transition (only
   advance toward terminal states; ignore regressions) or document why last-write-wins is
   acceptable here. If unsure, leave `order_events` (source of truth) as-is and only harden the
   derived `orders` projection.
6. **`OrderGovernor.__init__` dead clause:** `max_per_sec > 2 or max_per_sec >= 10` — the
   second clause is unreachable. Simplify to `max_per_sec > 2` (keep the message).
7. **Read-only console endpoints are unauthenticated** (`/`, `/api/*`, `/events`) — mitigated
   by the enforced loopback/Tailscale bind. Note this explicitly in `docs/` as an accepted
   risk, or add token-gating to the read endpoints if the operator wants defense in depth.
   (Decision item — default to documenting the accepted risk; the bind restriction is real.)
8. **`Brain/` carries a parallel `PaperBroker`/`LiveExecutor`** (live mode quarantined with a
   `raise` — good). Add a one-line note in `AGENTS.md`/`Brain` README that `xenalgo.execution`
   is the *only* sanctioned execution path and `Brain`'s executor is research-only, to prevent
   future drift. Do not delete or refactor `Brain` (out of scope per guardrails).

**Acceptance for Task 15:** All items applied; `.env.example` and `AGENTS.md` match reality;
governor daily-reset test added and green; full suite + coverage gates green.

---

## Definition of done (whole plan)

- Every task's new test fails on the pre-fix `main` and passes after its fix (spot-check by
  stashing the fix).
- `./_source/.venv/Scripts/python.exe -m pytest -q` green; `-m chaos` green.
- CI gates green: `--cov-fail-under=90` overall and `--fail-under=100` on
  `xenalgo/risk.py` + `xenalgo/execution/*`.
- A real process-restart integration test exists and passes (Tasks 2/7/11).
- A full paper session runs end-to-end on injected data with **real** fill prices and clean
  reconciliation (Tasks 1/3).
- `git diff` shows **no edits** to `Strategies/` or `Brain/` research math.
- `live_trading.enabled=false` and `broker.order_api_enabled=false` in every config; no code
  path can reach a live order API; `live_order_api_calls == 0` semantics preserved.
- README/`docs/DEPLOYMENT_STATUS.md` wording matches actual capability (no overclaim of
  external deployment proof).
- No secrets added anywhere.
```
