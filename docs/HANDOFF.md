# XenAlgo Handoff

**Last updated:** 2026-07-05  
**Current phase:** Phase 3.1 failure-injection suite implemented and locally green; Oracle-host proof still pending.
**Working directory:** `D:\XOLVER\XenAlgo`

## Safety Posture

XenAlgo is a real-money NSE trading system design. No live Dhan order API path was called,
tested, or enabled during Phase 1 or Phase 2. The live config keeps both
`live_trading.enabled` and `broker.order_api_enabled` set to `false`; the implemented
end-to-end path remains paper-mode only.

Phase 1 executable specs now run rather than skip. `ExecutionEngine.submit()` calls
`RiskEngine.check()` before broker submission, and idempotency still adopts an existing
correlation id instead of re-posting an order.

Phase 2 adds operator visibility and control surfaces only. The dashboard reads paper/live
state from SQLite, derives positions by replaying confirmed `TRADED` journal events, and
limits writes to authenticated operator controls in `risk_state` plus append-only
`audit_log` entries. It does not add a Dhan order-placement path.

Phase 3.1 adds only local deterministic failure-injection coverage and paper-mode safety
guards. It does not enable live trading, does not call the live Dhan order API, and does not
change `live_trading.enabled=false` or `broker.order_api_enabled=false`.

## Completed In Phase 0

- Promoted `_source/Brain` to root `Brain/`.
- Promoted `_source/Strategies` to root `Strategies/`.
- Verified promoted research files are byte-identical to `_source` for the checked modules.
- Added the live-system scaffold package under `xenalgo/`:
  - `xenalgo.config` loads and validates config profiles.
  - `xenalgo.logging_setup` emits structured JSON logs with a run id.
  - `python -m xenalgo --profile live|research` validates config and prints checksum metadata.
- Split config into:
  - `config/config.research.yaml`
  - `config/config.live.yaml`
  - `config/nse_overrides.yaml`
- Added dependency and build hygiene:
  - `requirements.in`
  - `requirements.txt`
  - `requirements.lock`
  - `pyproject.toml`
  - `Dockerfile`
  - `.dockerignore`
  - `.gitignore`
  - `.env.example`
- Added GitHub Actions CI definition at `.github/workflows/ci.yml`.
- Updated `pytest.ini` so the root suite includes both `tests/` and `_source/Lab`.
- Added Phase 0 tests at `tests/test_phase0_scaffold.py`.
- Added operator infra runbook at `docs/PHASE0_OPERATIONS.md`.

## Completed In Phase 1

- Added the append-only SQLite journal and order state machine in `xenalgo/execution/`.
- Added `PositionBook`, idempotent fill application, `FillListener`, and restart replay.
- Added `ExecutionEngine` with correlation-id adoption, write-ahead intent, rejection
  recording, consecutive-failure halting, kill-switch support, and mandatory risk checks.
- Added pure `RiskEngine` with notional, ADV, price-collar, position-cap, cash, duplicate,
  restricted-list, and breaker checks.
- Added the order governor token bucket and daily cap in `xenalgo/broker/governor.py`.
- Added paper-mode broker, token manager, in-memory alerter, scheduler guards, data
  freshness/sanity gates, sleeve allocator/netting, kill switch, deploy guard, and reconciler.
- Added a paper-day integration runner that performs token -> data -> risk -> order ->
  confirmed fill -> reconciliation -> alert without live broker calls.
- Updated the stale Phase 0 scaffold test so Phase 1 modules are expected to import.

## Completed In Phase 2

- Added `xenalgo.web.ConsoleStore` for dashboard snapshots backed by SQLite.
  - Reads `orders`, `order_events`, `risk_state`, `portfolio_snapshots`, and `audit_log`.
  - Derives displayed positions from confirmed `TRADED` journal events, preserving the
    positions-change-only-from-fills invariant.
  - Recovers sleeve attribution from prior order events when fill events carry
    `sleeve=unknown`.
- Added the FastAPI operator console in `xenalgo/web/app.py`.
  - `GET /` renders an HTML dashboard for overview, risk state, positions, orders, and
    recent journal events.
  - `GET /api/snapshot` exposes the same read model as JSON.
  - `GET /events` serves SSE snapshots; `?once=true` is available for deterministic smoke
    tests.
  - `POST /control/kill` activates the persistent kill switch and blocks new submissions.
  - `POST /control/rearm/{breaker}` clears an approved breaker key and audit-logs the
    action.
  - `POST /postback` validates an HMAC signature and records a postback enqueue audit entry
    only; it does not apply fills or submit/cancel orders.
- Added `xenalgo.web.TelegramCommandRouter` for `/status`, `/positions`, `/kill`, and
  `/rearm <breaker>` command behavior against the same store.
- Added `xenalgo.web.server` bootstrap:
  - Loads the live config and journal path.
  - Requires `XENALGO_CONSOLE_TOKEN` for operator controls.
  - Refuses wildcard public binds (`0.0.0.0` / `::`) so the console runs on loopback or the
    configured Tailscale interface.
  - Keeps the public postback endpoint disabled unless the live config enables it and a
    `POSTBACK_HMAC_SECRET` is present.
- Added Phase 2 integration tests at `tests/integration/test_phase2_console.py`.

## Completed In Phase 3.1

- Expanded the chaos suite at `tests/chaos/test_failure_injection.py` to cover the full
  Phase 3.1 failure list from `docs/BUILD_PLAN.md`:
  - crash/restart mid-order without duplicate submission,
  - dropped WebSocket fill channel with REST fallback recovery,
  - duplicate fill events from redundant channels as a no-op,
  - token expiry blocking order submission before broker access,
  - corrupt candle rejection before sizing/order flow,
  - rejection storm tripping the consecutive-failure breaker,
  - reconciliation drift signaling a halt,
  - broker/network partition journaled as a rejected submission instead of crashing,
  - clock skew blocking time-sensitive scheduler gates.
- Added `xenalgo.data.CorruptDataError` and `assert_latest_prices_sane()`; the paper-day
  runner now applies this price sanity gate after freshness validation.
- Added `xenalgo.scheduler.ClockSkewError` and `assert_clock_in_sync()` for host-clock
  drift detection.
- Hardened `ExecutionEngine.submit()` so broker submission exceptions are converted into
  append-only `REJECTED` journal events, increment the failure counter, and can trip the
  existing failure breaker.

## Verification Evidence

Run from repo root:

```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
```

Last observed result:

```text
85 passed, 1 warning
```

Run from `_source`:

```powershell
./.venv/Scripts/python.exe -m pytest Lab/ -q
```

Last observed result:

```text
4 passed
```

Targeted Phase 3.1 verification:

```powershell
./_source/.venv/Scripts/python.exe -m pytest tests/chaos -q
```

Last observed result:

```text
9 passed
```

Targeted Phase 2 verification:

```powershell
./_source/.venv/Scripts/python.exe -m pytest tests/integration/test_phase2_console.py tests/test_phase0_scaffold.py -q
```

Last observed result:

```text
13 passed, 1 warning
```

Config validation:

```powershell
./_source/.venv/Scripts/python.exe -m xenalgo --profile live
./_source/.venv/Scripts/python.exe -m xenalgo --profile research
```

Both profiles loaded and emitted checksum metadata.

## Known Non-Repo / Operator-Side Work

Phase 0 task `0.1a` includes Oracle Cloud and Tailscale provisioning. The repo now contains
the Docker artifact and an operations runbook, but the actual cloud work still requires the
operator's OCI and Tailscale access:

- Provision Oracle Cloud Always Free ARM instance in Mumbai or Hyderabad.
- Reserve and attach the public IP.
- Install Docker and Tailscale.
- Close inbound ports except SSH.
- Confirm the app image validates with `.env` on the host.
- Set `XENALGO_CONSOLE_TOKEN` on the host before running the console.
- Set `TAILSCALE_BIND_HOST` to the host's Tailscale IP/interface address before exposing the
  dashboard beyond loopback.
- Keep `web.public_postback_enabled=false` until the isolated webhook endpoint is explicitly
  deployed with `POSTBACK_HMAC_SECRET` and port exposure is reviewed.

Follow `docs/PHASE0_OPERATIONS.md` for the checklist.

## Phase 2 Limitations / Next Engineering Boundary

The paper-mode core is implemented and tested locally. The production Dhan REST/WebSocket
gateway is still intentionally not live-enabled in this checkout; before any real broker
integration, keep `broker.order_api_enabled=false`, use HTTP-level mocks only, and require an
explicit operator approval for any change that could touch real orders.

Phase 2's repository code is implemented, but G2's network assertions still require
environment-side proof on the Oracle/Tailscale host:

- Dashboard fill reflection is covered locally through the SSE/snapshot path; verify
  <=3 seconds on the deployed paper host once Oracle is provisioned.
- Dashboard kill switch is covered locally and blocks submission in under 1 second; repeat
  the timed check from phone/laptop over Tailscale.
- Prove off-tailnet refusal with a port scan once the host exists.
- Keep the postback endpoint disabled until the HMAC secret and isolated public ingress are
  reviewed.

Phase 3.1's repository failure-injection suite is implemented and locally green. The
`docs/BUILD_PLAN.md` wording also says the suite runs on the Oracle dev host; that
environment-side execution is still pending until the Oracle/Tailscale paper host is
provisioned.

## Git / Workspace Notes

The root `D:\XOLVER\XenAlgo` directory is now initialized as the XenAlgo Git repository.
`_source/` remains a separate cloned research snapshot and is represented from the root repo
as an explicit submodule (`.gitmodules`) pointing to:

```text
https://github.com/anishbaral2012/quant-swing-trade.git
```

GitHub Actions checks out submodules so root tests that compare promoted files against
`_source/` and run `_source/Lab` continue to work. Do not commit `_source/.venv/`, `.env`,
`*.duckdb`, `Diary/`, `Supply/`, or secret material.

## Generated Artifacts

Running the promoted research tests from repo root can create transient `Lab/` and `Diary/`
folders. They are ignored by `.gitignore`; remove them after verification if they appear.

## Next Safe Step

Provision the Oracle/Tailscale paper host from `docs/PHASE0_OPERATIONS.md`, run the Phase 2
console there with `XENALGO_CONSOLE_TOKEN` and `TAILSCALE_BIND_HOST`, and capture G2 network
evidence. Then run the now-complete Phase 3.1 chaos suite on that host and attach the host
evidence before starting the 4-week paper burn-in. Do not introduce a live Dhan order path
without a separate, explicit operator request.
