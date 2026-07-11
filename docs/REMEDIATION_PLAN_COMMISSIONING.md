# Commissioning Remediation Plan


Status: **COMPLETE - Batches A-G implemented in this checkout.**
Scope: the eight P1 findings plus code-level P2 blockers confirmed against source on this branch, **plus a full broker migration from Dhan to Fyers (execution AND market data)** per operator decision.
Method for every item: **write a failing regression test that reproduces the defect first, then fix, then confirm the test passes and the suite stays green.**

Findings verified in code (not hallucinated). Anchors are the current lines on `main`.

> **Broker migration note.** Operator has decided to replace Dhan with **Fyers** as the sole broker and data source, and to retarget now (before building the live gateway/postback). This reshapes C2 and C3 below and adds Batches F and G. Note: the historical OHLCV is exchange truth and does not change with the broker, so the alphas do **not** need re-validating — Batch G is a **data-parity reconciliation** (confirm Fyers-sourced history matches the already-validated dataset, chiefly on corporate-action adjustment), not a re-backtest. The recorded "re-validation risk" at [PLAN.md:201](../PLAN.md) is therefore narrowed to a cheap data-QA check.
>
> Fyers v3 API facts grounding this plan (from official docs + KB): OAuth2 auth-code → daily access token; order/fill delivery via **Order WebSocket** (`onOrder`/`onTrade`), **no HTTP postback webhook**; `filledQty` is cumulative; symbols are strings (`NSE:SBIN-EQ`) not numeric `security_id`; rate limits 10/s · 200/min · 100k/day. Sources cited at end.

---

## Sequencing

The execution-path items share the same objects, so they are done as one coherent change set rather than eight isolated patches:

1. **Batch A — Execution core** (Findings 1, 2, 5 + P2 state-machine): single-engine lifecycle, governor wiring, position-aware risk context, state-machine routing. These all touch `ExecutionEngine` / `PaperDayRunner`.
2. **Batch B — Fill accounting** (Finding 3): `PositionBook.apply_fill` + `ConsoleStore._positions_from_events` cumulative semantics.
3. **Batch C — Surface hardening** (Findings 6, 7, 8): Fyers Order-WS fill channel (replaces Dhan postback), token at rest + Fyers OAuth, bind guard.
4. **Batch D — Legacy quarantine** (Finding 4): delete the `Brain` live route.
5. **Batch E — CI enforcement** (P2 coverage).
6. **Batch F — Fyers broker + data migration**: symbol model, Fyers order gateway, data-layer migration, config/env/docs retarget. Underpins C2/C3.
7. **Batch G — Data-parity reconciliation**: confirm Fyers-sourced history matches the validated dataset (corporate-action adjustment + universe). Cheap data-QA check, **not** a re-backtest.

Each batch is independently testable and independently reviewable. Dependency note: F1 (symbol model) and the Fyers auth provider (C3) land early since A/B/C's fill and gateway work reference them; G runs last and gates go-live.

---

## Batch A — Execution core

Implementation status: **COMPLETE** as of 2026-07-11.

Verification:
- `./_source/.venv/Scripts/python.exe -m pytest tests/unit/test_governor.py tests/unit/test_execution_phase_a.py tests/integration/test_phase1_paper_day.py tests/chaos/test_failure_injection.py -q --basetemp .tmp/pytest-phase-a` -> 20 passed.
- `./_source/.venv/Scripts/python.exe -m pytest -q --basetemp .tmp/pytest-full-phase-a` -> 120 passed.

What landed:
- One `ExecutionEngine` is reused for the paper-day loop.
- Consecutive execution failures and the halted state persist in `risk_state` and survive engine reconstruction.
- Risk checks can receive a live per-order `RiskContext`; `PaperDayRunner` now supplies current position/cash context from the fill listener and broker.
- `OrderGovernor.allow()` enforces the token bucket and daily cap, and `ExecutionEngine` rejects rate-limited orders before broker submission without counting them toward the failure breaker.
- Submission now journals the legal audit sequence `INTENT -> SUBMITTED -> PENDING/REJECTED` through `OrderStateMachine`.

### A1. Single engine per day + persistent breaker (Finding 5)
- **Root cause:** [monolith.py:84](../xenalgo/monolith.py) constructs a new `ExecutionEngine` inside the per-order loop, resetting `_failures`/`_halted` every order.
- **Fix:** construct `ExecutionEngine` **once** before the loop; reuse it for every `submit`. The rejection-storm breaker then accumulates across orders as designed.
- **Restart persistence:** `_failures`/`_halted` are in-memory. Persist consecutive-failure count and halt state to the journal (`risk_state` table already exists in `state.py`) so a restart mid-storm stays halted. Load it on engine construction.
- **Test:** `test_rejection_storm_halts_within_day` — feed 4 orders that the risk engine rejects; assert broker `place_order` is called at most `consecutive_failure_halt` times and the 4th+ returns `REJECTED reason=halted`. Second test: construct engine, trip halt, rebuild engine from same journal, assert still halted.
- **Decision needed:** none.

### A2. Position-aware risk context (Finding 1)
- **Root cause:** [monolith.py:82](../xenalgo/monolith.py) passes `positions={}`; the cap check at [risk.py:80](../xenalgo/risk.py) therefore never sees existing holdings. Compounded by A1's per-order engine.
- **Fix:** the risk context must reflect the **live book** at each submission. Approach: give `ExecutionEngine.submit` an up-to-date positions view sourced from the same `PositionBook` the `FillListener` maintains. Concretely — add a `risk_context_provider: Callable[[OrderRequest], RiskContext]` (or a `positions` accessor) to the engine, and have `PaperDayRunner` supply current `{symbol: {"qty": book.qty(symbol)}}` from the listener book plus current cash. The static `risk_context=ctx` built once at loop top is removed.
- **Consequence:** two 10% buys in the same symbol now correctly scale/reject the second (`position cap reached` / `10% position cap`). Reconciliation still passes because book and broker agree — but now at the *correct* capped exposure.
- **Test:** `test_second_buy_respects_position_cap` — two valid buys of one symbol, each sized at the 10% cap; assert combined filled qty ≤ cap and the second is SCALED or REJECTED. Guard against regression of the reconciliation-clean-at-20% behavior.
- **Decision needed:** confirm cap semantics on the second order should **scale-to-fit** (fill the remainder up to cap) vs **hard-reject**. Current risk engine already scales; I'll keep scale unless you want hard-reject.

### A3. Governor enforced and wired (Finding 2)
- **Root cause:** [governor.py:48](../xenalgo/broker/governor.py) `allow()` never calls `self.bucket.try_acquire()`; and `OrderGovernor` is instantiated only in tests — not connected to `ExecutionEngine`.
- **Fix (two parts):**
  1. `allow()` must consult the token bucket **and** the daily cap: return `False` if either the bucket rejects or the daily cap is hit; only decrement/increment when actually granting.
  2. Inject an `OrderGovernor` into `ExecutionEngine`; call it immediately before `broker.place_order`. On denial, journal a `REJECTED reason="rate limited"` (or `daily cap reached`) and return without hitting the broker.
- **Test:** `test_governor_blocks_burst_end_to_end` — submit 100 orders instantly through the engine with a real `OrderGovernor(max_per_sec=2)`; assert broker `place_order` count ≤ bucket capacity within the first second (reproduces the "100 accepted" defect). Plus a unit test that `allow()` returns `False` when the bucket is empty even under the daily cap.
- **Decisions needed:**
  - **Over-limit behavior:** *reject* the order (fits the daily-batch paper model, simplest, fail-safe) vs *block/sleep* until a token is available. I recommend **reject** for the paper daemon — a queued sleep hides throughput problems. Confirm.
  - Should a rate-limit rejection count toward the consecutive-failure breaker? I recommend **no** (it's not a broker/risk failure). Confirm.

### A4. State-machine routing + SUBMITTED (P2 bypass)
- **Root cause:** `submit()` journals `INTENT` ([:357](../xenalgo/execution/__init__.py)) then `PENDING` ([:369](../xenalgo/execution/__init__.py)) directly via `journal.append`, skipping `SUBMITTED`. `INTENT→PENDING` is illegal per `LEGAL_TRANSITIONS`; `OrderStateMachine.to()` (which would validate) is never used on this path.
- **Fix:** route state changes through `OrderStateMachine.to()` so illegal transitions raise instead of being silently written. Emit the legal sequence: `INTENT → SUBMITTED` (immediately before the broker call) `→ PENDING` (on ack) or `→ REJECTED`. `SUBMITTED` is a recorded state, giving a real audit point for "sent to broker but not yet acked."
- **Test:** `test_order_records_submitted_before_pending` — assert the journal event sequence for an accepted order is exactly `INTENT, SUBMITTED, PENDING`. `test_illegal_transition_raises` — attempt a direct `INTENT→PENDING` and assert `IllegalTransition`.
- **Decision needed:** none, but note this changes journal event counts — Batch B replay and any dashboards counting events must be checked (they filter on `state`, so low risk).

---

## Batch B — Fill accounting (Finding 3)

Implementation status: **COMPLETE** as of 2026-07-11.

Verification:
- `./_source/.venv/Scripts/python.exe -m pytest tests/unit/test_order_state_machine.py tests/integration/test_phase2_console.py -q --basetemp .tmp/pytest-phase-b-related` -> 23 passed.
- `./_source/.venv/Scripts/python.exe -m pytest -q --basetemp .tmp/pytest-full-phase-b` -> 122 passed.

What landed:
- `Fill` can carry `PART_TRADED` vs `TRADED` state while keeping `TRADED` as the default.
- `PositionBook.apply_fill` and `PositionBook.from_replay` now treat `filled_qty` as cumulative per broker order (`broker_order_id`, falling back to `correlation_id`) and apply only the increase since the last seen cumulative quantity.
- Duplicate events still no-op via `applied_events`; duplicate cumulative updates from a redundant channel apply a zero delta instead of overstating the book.
- `ConsoleStore._positions_from_events` mirrors the same cumulative replay logic and includes `PART_TRADED` events in derived positions.

- **Root cause:** [execution/__init__.py:258](../xenalgo/execution/__init__.py) adds every `filled_qty` as a delta; [state.py:330](../xenalgo/web/state.py) sums `filled_qty` per TRADED event. Dhan's `filled_qty` is **cumulative-to-date**, so `PART_TRADED(4)` then `TRADED(10)` → 14 instead of 10.
- **Fix:** treat `filled_qty` as cumulative per broker order. `PositionBook` tracks last-seen cumulative fill per `broker_order_id` (fallback `correlation_id`); the applied delta is `new_cumulative − prev_cumulative`. Idempotent replays and the `applied_events` dedup are preserved (a repeated identical cumulative yields delta 0). Mirror the identical logic in `ConsoleStore._positions_from_events` and `PositionBook.from_replay`.
- **Note:** this does not manifest in the current paper path (one synthetic fill per order) but is a hard correctness bug the instant real/postback partial fills arrive — must land before commissioning.
- **Test:** `test_cumulative_partial_fills_do_not_overstate` — apply `PART_TRADED qty=4` then `TRADED qty=10` for one order; assert position is 10. Replay-from-journal variant asserting the same. Idempotency test: applying the final `TRADED(10)` twice still yields 10.
- **Decision needed:** confirm Dhan's field is cumulative for both `PART_TRADED` and `TRADED` (the review cites Dhan's postback docs; I'll re-verify against the live Dhan contract as part of this batch since Batch C touches the same contract).

---

## Batch C — Surface hardening

Implementation status: **COMPLETE** as of 2026-07-11.

Verification:
- `./_source/.venv/Scripts/python.exe -m pytest tests/unit/test_commissioning_c_to_g.py tests/integration/test_phase2_console.py tests/test_phase0_scaffold.py -q --basetemp .tmp/pytest-cg-focused` -> 26 passed.

What landed:
- Console bind validation now allows only loopback or `100.64.0.0/10` Tailscale CGNAT IPs and rejects public IPs fail-closed.
- The Dhan `/postback` route and `ConsoleStore.record_postback()` audit-only path were removed.
- `FyersOrderFillConsumer` converts Fyers Order WebSocket/orderbook payloads into the same idempotent cumulative-fill path used by `FillListener` and `PositionBook`.
- `TokenManager` is broker-neutral, stores under the `fyers` token name, restricts POSIX file permissions to `0600`, and is paired with a mockable `FyersOAuthProvider`.
- Token store backup exclusion is enforced through the new `token_store_excluded_from_backup()` helper and `.xenalgo-secrets/` is gitignored.

### C1. Bind guard fail-closed (Finding 8)
- **Root cause:** [server.py:38](../xenalgo/web/server.py) rejects only `{"0.0.0.0","::"}`; `8.8.8.8` and any public IP pass, despite the message promising loopback/Tailscale only.
- **Fix:** validate with `ipaddress`: allow only loopback (`127.0.0.0/8`, `::1`) or the Tailscale CGNAT range (`100.64.0.0/10`). Everything else raises. Fail-closed.
- **Test:** `test_bind_guard_rejects_public_ip` (`8.8.8.8` → raises), `test_bind_guard_allows_loopback_and_tailscale` (`127.0.0.1`, `100.x.y.z` → ok), `test_bind_guard_rejects_wildcard` (unchanged).
- **Decision needed:** confirm the allowed Tailscale range is the standard `100.64.0.0/10`, and whether any additional interface (e.g. a specific LAN host) must be allowlisted via config.

### C2. Real fill channel via Fyers Order WebSocket (Finding 6) — RESHAPED by Fyers migration
- **Root cause (original):** [app.py:130](../xenalgo/web/app.py) requires a custom `x-xenalgo-postback-signature` HMAC that Dhan does not send; [state.py:259](../xenalgo/web/state.py) `record_postback` only writes an `audit_log` row while the endpoint returns `{"enqueued": True}` — no fill is enqueued or applied.
- **What changes under Fyers:** Fyers has **no HTTP postback webhook**. Its primary order/fill delivery is the **Order WebSocket** (`onOrder`/`onTrade`). So we do **not** port the Dhan postback endpoint. Instead:
  1. **Remove the Dhan `/postback` endpoint** (and its HMAC path) from [app.py](../xenalgo/web/app.py) and `record_postback` from [state.py](../xenalgo/web/state.py). This also removes the only reason the console needed a public port — reinforcing Tailscale-only and shrinking Finding 8's exposure.
  2. **Build the Fyers Order-WS fill consumer** as the real fill channel: a supervised WebSocket client whose `onOrder`/`onTrade` callbacks feed each update through the **same idempotent fill path** as Batch B (journal `applied_events` dedup → `PositionBook`/journal update, cumulative-`filledQty` delta). Lives in the execution/broker layer, consumed by `FillListener` — not the web process.
  3. **Redundant channel = REST orderbook poll:** a periodic `get_orderbook()` reconciliation replaces the Dhan "second webhook" as the backup fill source, reusing the same idempotent apply. Preserves the dual-channel design with no public port.
- **Test:** `test_fyers_order_ws_applies_fill_idempotently` — feed a Fyers-shaped `onTrade` cumulative payload; position updates once, duplicate is a no-op. `test_orderbook_poll_backfills_missed_fill` — WS drop, REST poll applies the fill exactly once. `test_dhan_postback_endpoint_removed` — `/postback` route no longer exists.
- **To pin during implementation:** exact order-socket traded-qty field name + status enum from Fyers docs; WS auth (access-token based); WS supervisor force-reconnects on hang (same posture PLAN.md prescribed for the Dhan SDK).

### C3. Token at rest + Fyers OAuth provider (Finding 7) — RESHAPED by Fyers migration
- **Root cause:** [token.py:59](../xenalgo/broker/token.py) writes the raw token into SQLite; [AGENTS.md:26](../AGENTS.md) requires tokens never be persisted to git or backups, and the scheduler runs `backups: "02:00"` over `Diary/`.
- **At-rest fix (unchanged decision):** keep the token store **out of backup scope** and off git — a dedicated ephemeral path excluded from the backup job and `.gitignore`, file permissions 0600. Satisfies AGENTS without key-management overhead.
- **Fyers auth provider (new):** the `TokenManager` shape (injected `token_provider` → `Token{value, expiry}`) is broker-neutral and stays. Implement a **Fyers OAuth2 provider**: `generate_authcode()` → login (PIN + TOTP) → `auth_code` → `generate_token()` → daily access token, with expiry set to the Fyers token lifetime. Refresh-token support (if used) to be pinned from Fyers docs. Config env vars change from Dhan (`DHAN_PIN`/`DHAN_TOTP_SECRET`/`DHAN_ACCESS_TOKEN`) to Fyers (`FYERS_APP_ID`/`FYERS_SECRET_KEY`/`FYERS_REDIRECT_URI`/`FYERS_PIN`/`FYERS_TOTP_SECRET`).
- **Test:** `test_token_store_excluded_from_backup_manifest`, `test_token_file_permissions` (0600 POSIX; skipped Windows), `test_fyers_token_provider_returns_valid_token` (mocked auth-code exchange → non-expired token), `test_expired_fyers_token_blocks_trading` (reuses existing `TradingBlocked` path).
- **To confirm:** exact Fyers token validity + whether we use the refresh-token flow; the exact backup job definition so the exclusion is wired where the backup actually runs.

---

## Batch D — Legacy `Brain` live route (Finding 4)

Implementation status: **COMPLETE** as of 2026-07-11.

What landed:
- `Brain.executor.LiveExecutor(mode="live")` now raises immediately.
- `Brain/order_manager.py` was deleted, removing the dormant `dhanhq` live-order wrapper from the promoted research tree.

- **Root cause:** [Brain/executor.py:83](../Brain/executor.py) instantiates `LiveOrderManager` (real `dhanhq`, default `MARKET` at [order_manager.py:55](../Brain/order_manager.py)); [Brain/executor.py:290](../Brain/executor.py) mutates positions on `PENDING`/`ACCEPTED`, bypassing the xenalgo journal, governor, and `RiskEngine`. Not on the deployed path, but live-capable code that violates the single-choke-point directive.
- **Options:**
  - **D-delete:** remove the `mode="live"` branch and the `LiveOrderManager` import from `Brain/executor.py` (and the class if nothing else uses it). Cleanest; eliminates the route entirely.
  - **D-quarantine:** hard-gate instantiation behind an explicit, non-default safety flag that raises unless set, and stop treating `PENDING`/`ACCEPTED` as fills. Keeps the code for future reference.
- **Recommendation:** **D-delete**, since the deployed entrypoint never uses it and the only sanctioned live path must go through `xenalgo` execution. Preserve nothing that can place a real order outside the journal/governor/risk chain.
- **Test:** `test_brain_executor_has_no_live_order_route` — assert `LiveOrderManager` is not importable/instantiable from `Brain.executor` (or that live mode raises). Grep-style guard test to prevent reintroduction.
- **Decision needed (blocking):** **delete** vs **quarantine**.

---

## Batch E — CI coverage enforcement (P2)

Implementation status: **COMPLETE** as of 2026-07-11.

What landed:
- `pytest-cov==7.0.0` is pinned.
- GitHub Actions runs the full suite with `--cov=xenalgo --cov-fail-under=90`.
- A second safety-critical gate runs coverage over the risk/execution test bundle and fails under 100% for `xenalgo/risk.py` plus `xenalgo/execution/*`.

- **Root cause:** [ci.yml:19](../.github/workflows/ci.yml) runs only `pytest -q`; `coverage` is not installed, so the ≥90% overall / 100% risk+execution targets are unenforced.
- **Fix:** add `pytest-cov` (or `coverage`) to `requirements.lock`; run `pytest --cov=xenalgo --cov-fail-under=90` and a targeted 100% gate on `xenalgo/risk.py` + `xenalgo/execution/` (separate `--cov` invocation or `coverage report --include` with `--fail-under=100`). CI fails if thresholds are missed.
- **Test:** CI itself is the test; add a local `make coverage` / documented command. Verify the new gate actually fails when a risk/execution line is uncovered (temporarily drop a test locally to confirm the gate bites).
- **Decision needed:** confirm the exact thresholds (≥90% overall, 100% on `risk`+`execution`) match the documented SUCCESS_CRITERIA so CI and docs agree.

---

## Batch F — Fyers broker + data migration (execution + data)

Implementation status: **COMPLETE** as of 2026-07-11.

What landed:
- `FyersSymbolResolver` maps NSE equity symbols to `NSE:<SYM>-EQ`.
- `FyersGateway` implements the existing broker contract shape with injected SDK client, `MARKETABLE_LIMIT`/CNC payload mapping, Fyers `tag` idempotency, orderbook lookup, modify/cancel, positions, holdings, and funds pass-throughs.
- `FyersHistoryLoader` calls an injected Fyers history client, chunks long date ranges, and normalizes daily candles into the existing `daily_ohlcv` shape.
- Live config, env examples, deployment env template, dependency pins, and config validation are retargeted to Fyers.
- `dhanhq` is removed from dependency pins. `fyers-apiv3` is intentionally not installed in CI because current Fyers SDK releases still pin `aiohttp==3.9.3`, which does not install cleanly in this Python 3.14 Windows toolchain; the live boundary uses an injected SDK/REST client so tests remain mock-only and no live API is imported.

Foundational: this underpins C2 (Order-WS fills) and C3 (OAuth token). Done before the live gateway is wired.

### F1. Symbol/identity model: `security_id` → Fyers symbol string
- **Root cause:** the codebase carries Dhan numeric `security_id` (e.g. `"2885"`) through `OrderRequest`, the journal `security_id` column, the paper broker, and `security_map`. Fyers identifies instruments by string (`NSE:RELIANCE-EQ`).
- **Fix:** introduce a Fyers symbol resolver (`symbol` → `NSE:<SYM>-EQ`) sourced from the Fyers symbol master; keep `security_id` as the Fyers symbol string end-to-end (no schema break — it's a `TEXT` column). Update fixtures/contract tests that hardcode `"2885"`.
- **Test:** `test_fyers_symbol_resolution` (RELIANCE → `NSE:RELIANCE-EQ`); update `test_broker_contract.py` fixtures.

### F2. Fyers order gateway (net-new; replaces the never-built DhanGateway)
- **Context:** `DhanGateway` was intentionally never implemented ([test_broker_contract.py](../tests/contract/test_broker_contract.py) header). We build a **FyersGateway** implementing the same `place_order/cancel_order/modify_order/get_orderbook/get_positions` contract the `PaperBroker` already satisfies, so paper and live differ only at the gateway boundary.
- **Fix:** wrap `fyers_apiv3` REST: map our `OrderRequest` → Fyers fields (`symbol`, `qty`, `type` 1=limit/2=market, `side` 1/-1, `productType=CNC` for delivery/swing, `limitPrice`, `validity`). Idempotency by `correlation_id` via Fyers order tag. Governor (Batch A3) sits in front — Fyers' own 10/s limit is the hard ceiling, our 2/s stays well under.
- **Test:** HTTP-mocked `test_fyers_gateway_places_and_maps_order`, `test_fyers_gateway_idempotent_by_tag`, `test_fyers_gateway_rejection_maps_to_state`. No live API calls in tests.
- **Decision needed:** default live order type — `MARKETABLE_LIMIT` (config already says this; safest for swing) vs plain `LIMIT`. Recommend keeping marketable-limit with the configured buy collar.

### F3. Data layer migration: Dhan history → Fyers history
- **Root cause:** [Brain/data_manager.py:29-33](../Brain/data_manager.py) pulls historical OHLCV, scrip master, and NIFTY-200/500 universe from Dhan.
- **Fix:** replace with Fyers `history()` (`symbol`, `resolution="D"`, epoch `range_from`/`range_to`, `date_format`) into the same DuckDB `daily_ohlcv` schema; source the universe/symbol master from Fyers. Respect Fyers per-request date-range limits (chunk long ranges). Update the synthetic-mode credential check to Fyers keys.
- **Test:** mocked-response `test_fyers_history_loads_into_duckdb`, `test_history_chunks_long_ranges`, `test_synthetic_mode_on_missing_fyers_keys`.
- **Note:** this is the change that triggers Batch G.

### F4. Config, env, deploy, and docs retarget
- **Fix:** `config.live.yaml` `broker:` section → Fyers (`provider: fyers`, app-id/secret/redirect/pin/totp env names, `fyers_sdk_version` pinned); `config.py` validation updated; `.env.example`, `deploy/oracle/xenalgo.env.example`, `requirements.{in,lock,txt}` (`dhanhq` → `fyers-apiv3`); scrub Dhan references across the 43 docs/config files (rate limits → Fyers 10/s; symbol examples). **Retain** the static-IP-registration commissioning gate (per decision 9 — kept for a possible future Jantra API switch even though Fyers OAuth doesn't require it). Document the kill-switch Layer-4 change (per decision 8): Fyers has no broker-side kill-switch API; compensating controls are the dashboard button, Telegram `/kill`, session-token revocation, and the account-level capital cap.
- **Test:** `test_phase0_scaffold` and config tests updated to assert Fyers wiring; `pip check` clean on the new dep.

---

## Batch G — Data-parity reconciliation (NOT a re-backtest)

Implementation status: **COMPLETE** as of 2026-07-11.

What landed:
- `panels_match_validated_baseline()` compares Fyers-sourced candidate OHLC panels against the validated baseline within a configurable bps tolerance and checks universe membership.
- The default test tolerance is the plan default of a few bps (`5` bps).
- This remains a data-QA gate, not a strategy re-backtest.

- **Why (corrected):** the historical OHLCV is exchange truth and does not change with the broker, so the alphas do **not** need re-validating. The only thing that can legitimately differ between two vendors is the **corporate-action adjustment convention** (how splits/bonuses/dividends are back-adjusted) and the **point-in-time universe list**. So this batch is a data-QA check, not a strategy re-run.
- **Work:** load the Fyers-sourced daily panel for the NIFTY-500 universe and **diff it against the existing validated dataset** (the DuckDB `daily_ohlcv` the alphas were validated on). Compare adjusted close/OHLC across corporate-action dates and check universe membership. If they reconcile within a small numerical tolerance → the validation carries over unchanged, no re-backtest.
- **Only if they diverge materially** (e.g. Fyers adjusts corporate actions differently): treat it as a data-quality issue — normalize the Fyers series to match the validated adjustment convention, or, if that's not possible, re-run the affected alpha on the corrected series. This is contingency, not the default path.
- **Gate:** parity check must pass (or divergences be explained/normalized) before live — but this is a **data-integrity** gate, cheap to run, not a full validation cycle.
- **Test:** `test_fyers_panel_matches_validated_baseline` (reconcile a sample of symbols incl. ones with known splits/bonuses within tolerance); `test_universe_membership_matches`.
- **Decision needed:** the reconciliation tolerance (e.g. adjusted prices within a few bps) and which corporate-action names to spot-check.

---

## Out of scope for this plan (noted, not fixed here)

- **Compliance docs (P2) — partly absorbed by Batch F4:** the "Dhan 25/s" claim in [TRD.md:20](../docs/TRD.md) is superseded by **Fyers' 10/s** limit during the migration; the 2/s governor stays conservative. The remaining external claim to verify is [PRD.md:119](../docs/PRD.md) "no exchange algo ID required" — NSE may now require a generic algo ID + order tagging regardless of broker. Keep that as a cited docs/regulatory verification task.
- **Phase 3.2/3.3 evaluators encode superseded durations:** acknowledged in the handoff; their `passed` output stays non-authoritative until updated. Separate task.
- **Scheduled data-only paper daemon absent:** the deployed service is only the console. This is a build item, not a bug fix — commissioning can't fully start until it exists. Track separately.

---

## Decisions — RESOLVED (operator sign-off)

1. **A2** — second-order cap: **scale-to-fit** (fill remainder up to cap; risk engine's existing SCALE path).
2. **A3** — governor over-limit: **reject** the order (`REJECTED reason="rate limited"`, no broker call); rate-limit rejections do **not** count toward the consecutive-failure breaker.
3. **C2** — fill channel: **build the real fill channel now, Fyers-native** — Order WebSocket → idempotent apply, REST orderbook poll as backup, **remove** the Dhan `/postback` endpoint (no public port).
4. **C3** — token: **exclude-from-backup + 0600 perms**, plus a **Fyers OAuth2 provider** for `TokenManager`.
5. **D** — Brain live route: **delete** the `mode="live"` branch and `LiveOrderManager` wiring from `Brain/executor.py`.
6. **E** — coverage thresholds: **≥90% overall, 100% on `risk`+`execution`**, to match SUCCESS_CRITERIA.
7. **Broker scope** — Fyers replaces **execution AND market data**; retarget now (folds into C2/C3 + Batches F/G).
8. **Kill-switch Layer 4 gap:** **accepted.** Fyers has no broker-side kill-switch equivalent, and that is OK. Compensating controls: dashboard button, Telegram `/kill`, session-token revocation, and the account-level capital cap.
9. **Static-IP registration gate:** **keep it.** Do not drop the ≥7-day static-IP registration commissioning gate — retained for a possible future switch to the Jantra API, even though Fyers OAuth doesn't require it.
10. **F2 default live order type:** **`MARKETABLE_LIMIT`** + configured buy collar.

## Open decision — minor, has a default

11. **G reconciliation tolerance:** default to **adjusted prices matching within a few bps**, spot-checking a handful of known split/bonus names in the universe. Proceeding with this default unless you want a specific band. (Data-QA only — not a strategy re-validation.)

All substantive decisions resolved. **Ready to implement.** Suggested start: Batch A (execution-core safety fixes), which has no Fyers dependency. C depends on the Fyers auth provider (C3) landing first; F1/C3 land early so C and the gateway can reference them.
