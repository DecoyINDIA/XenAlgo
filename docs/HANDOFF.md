# XenAlgo Handoff

**Last updated:** 2026-07-05  
**Current phase:** Phase 3.4 repository-local evidence tooling implemented; actual Oracle-host proof, four-week paper burn-in, live-host migration, one-week live-host paper validation, operator-approved 10% live activation, and staged capital ramp are still pending operator/external gates.
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

Phase 3.2 repository-local work adds evidence evaluators and an operations runbook only. It
does not provision hosts, register Dhan static IPs, run calendar-time burn-in, call the live
Dhan order API, or enable live order placement.

Phase 3.3 repository-local work adds post-migration evidence evaluators and an operations
runbook only. It does not operate the paid live host for the required week, verify Dhan
static IPs through a real startup, call the live Dhan order API, or enable live order
placement.

Phase 3.4 repository-local work adds go-live checklist evidence evaluators and an operations
runbook only. It does not call Dhan, mutate config, fund the dedicated account, verify phone
alerts, or enable live order placement from this checkout.

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
- Updated `pytest.ini` so the root suite runs the committed repo tests under `tests/`.
- Added Phase 0 tests at `tests/test_phase0_scaffold.py`.
- Added operator infra runbook at `docs/PHASE0_OPERATIONS.md`.

## Completed In Phase 1

- Added the append-only SQLite journal and order state machine in `xenalgo/execution/`.
- Added `PositionBook`, idempotent fill application, `FillListener`, and restart replay.
- Hardened SQLite connection lifecycle for journal, token, kill-switch, and console-state
  stores so each operation explicitly commits/rolls back and closes its connection.
- Added Hypothesis property coverage for SI-3/SI-4: non-fill journal events never replay
  into positions, and duplicate fill event keys apply only once.
- Added a subprocess crash durability test for SI-9: a child process writes confirmed fills,
  is killed abruptly, and the parent verifies SQLite integrity plus replayed positions.
- Added `ExecutionEngine` with correlation-id adoption, write-ahead intent, rejection
  recording, consecutive-failure halting, kill-switch support, and mandatory risk checks.
- Tightened the restart idempotency proof to 1,000 simulated restart attempts with a
  single broker placement, matching `docs/SUCCESS_CRITERIA.md`.
- Added pure `RiskEngine` with notional, ADV, price-collar, position-cap, cash, duplicate,
  restricted-list, and breaker checks.
- Added the order governor token bucket and daily cap in `xenalgo/broker/governor.py`.
- Added paper-mode broker, token manager, in-memory alerter, scheduler guards, data
  freshness/sanity gates, sleeve allocator/netting, kill switch, deploy guard, and reconciler.
- Added `tests/contract/test_broker_contract.py` around the paper broker boundary:
  correlation-id idempotency, fill accounting from requested quantity, rejected/cancelled
  orders staying unfilled, and pending-order modify/cancel behavior.
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

## Completed In Phase 3.2 Repo-Local Readiness

- Added `xenalgo.phase32` for evaluating operator-supplied Phase 3.2 evidence:
  - `BurnInReview` checks four-week burn-in span, minimum reviewed trading days, complete
    sleeve coverage, per-sleeve daily deviation ratio, token refresh success, safety
    incidents, and unresolved outliers.
  - `evaluate_live_host_readiness()` checks India-region host selection, primary/secondary
    static IP evidence with at least seven-day lead time, Docker image reference, systemd,
    backups, restore drill, heartbeat, Oracle warm-staging retention, and live-order toggles
    remaining disabled before go-live.
  - `load_burn_in_csv()` reads the operator's non-secret burn-in evidence CSV.
- Added `tests/unit/test_phase32_readiness.py` to prove clean evidence passes and incomplete
  or unsafe evidence fails closed.
- Added `docs/PHASE3_2_OPERATIONS.md` with the burn-in CSV schema and live-host evidence
  checklist.
- Updated README, build plan, success criteria, test plan, and docs index to point at the
  Phase 3.2 evidence workflow.

## Completed In Phase 3.3 Repo-Local Readiness

- Added `xenalgo.phase33` for evaluating operator-supplied Phase 3.3 evidence:
  - `PostMigrationValidationReview` checks at least one calendar week of post-migration
    paper records, minimum reviewed trading sessions, complete sleeve coverage, host-id
    consistency, static-IP startup verification before validation starts, deviation ratio,
    token refresh success, clean reconciliation, no safety incidents, no unresolved
    outliers, and live-order toggles remaining disabled.
  - `PostMigrationHostEvidence` records the non-secret live-host facts needed for the
    evidence check, including provider/region, migration date, Docker image, config
    checksum, systemd/backups/heartbeat, and Phase 3.2 readiness status.
  - `load_post_migration_csv()` reads the operator's non-secret post-migration validation
    CSV.
- Added `tests/unit/test_phase33_readiness.py` to prove clean evidence passes and incomplete
  or unsafe evidence fails closed.
- Added `docs/PHASE3_3_OPERATIONS.md` with the post-migration CSV schema and live-host
  evidence checklist.
- Updated README, build plan, success criteria, test plan, and docs index to point at the
  Phase 3.3 evidence workflow.

## Completed In Phase 3.4 Repo-Local Readiness

- Added `xenalgo.phase34` for evaluating operator-supplied Phase 3.4 evidence:
  - `GoLiveChecklistReview` checks that G0, G1, G2, Phase 3.1, Phase 3.2 burn-in,
    Phase 3.2 live-host readiness, and Phase 3.3 post-migration evidence have passed.
  - It checks live-host id, config checksum, static-IP startup verification, at least five
    token-refresh sessions, live-host restore drill, broker-side kill switch proof,
    real-phone alert confirmation, dedicated funded account evidence, explicit operator
    approval, initial capital no greater than 10%, governor cap at or below 2 OPS, and
    off-market activation timing.
  - It supports a pre-activation review mode that requires live-order flags to remain off,
    plus an activation review mode for the separately approved 10% live stage.
- Added `tests/unit/test_phase34_go_live.py` to prove clean evidence passes and incomplete,
  over-sized, in-market, or accidentally enabled evidence fails closed.
- Added `docs/PHASE3_4_OPERATIONS.md` with the go-live checklist CSV schema and review
  commands.
- Updated README, build plan, success criteria, test plan, and docs index to point at the
  Phase 3.4 evidence workflow.

## Phase 3 Status Boundary

Phase 3.1, Phase 3.2 evidence tooling, Phase 3.3 evidence tooling, and Phase 3.4 evidence
tooling are the only Phase 3 items that are fully repo-local. They are locally verified
through deterministic tests only.
No live Dhan order API path was called, enabled, or tested.

The rest of Phase 3 cannot be truthfully completed from this checkout alone:

- Phase 3.2a still requires at least four calendar weeks of paper burn-in on live market
  data on the Oracle/Tailscale paper host, then evaluation of the collected evidence with
  `BurnInReview`.
- Phase 3.2b still requires selecting/provisioning the paid live host, deploying the same
  Docker image, setting up systemd/backups/heartbeat, and registering the new static IPs
  with Dhan at least seven days before go-live, then checking the evidence with
  `evaluate_live_host_readiness()`.
- Phase 3.3 requires at least one week of paper validation on the new live host after
  migration, then evaluation of the collected evidence with `PostMigrationValidationReview`.
- Phase 3.4 requires external/operator evidence for the go-live checklist before enabling
  live trading at 10% capital; `GoLiveChecklistReview` can evaluate that evidence, but the
  committed config still keeps live order placement disabled.
- Phase 3.5 requires the staged 10% -> 25% -> 50% -> 100% capital ramp with at least two
  clean weeks at each stage.

Until those external gates are evidenced, the repo status is: Phase 3.1 complete, Phase 3.2
evidence tooling complete, Phase 3.3 evidence tooling complete, and Phase 3.4 evidence
tooling complete; actual Phase 3.2/3.3/3.4 external proof and full G3 go-live are not
complete.

## Verification Evidence

Run from repo root:

```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
```

Last observed result:

```text
103 passed, 1 warning in 8.79s
```

Note: full-suite attempts can fail during pytest fixture setup if Windows points pytest at
an inaccessible temp directory. A rerun with `TMP` and `TEMP` set to a fresh repo-local
subdirectory, `D:\XOLVER\XenAlgo\.tmp\pytest-full-phase34-run`, passed.

Run from `_source`:

```powershell
./.venv/Scripts/python.exe -m pytest Lab/ -q
```

Last observed result:

```text
4 passed in 1.73s
```

CI checkout fix:

- GitHub Actions run `28727549195` failed during checkout because `actions/checkout` tried
  to initialize `_source` as a submodule from `https://github.com/anishbaral2012/quant-swing-trade.git`
  and GitHub returned `Repository not found`.
- `_source` is now treated as an optional local/operator research snapshot, not a required
  GitHub submodule. CI installs `requirements.lock` and runs the committed repo suite.
- `tests/test_phase0_scaffold.py` still verifies byte identity against `_source` when the
  local snapshot is present, and skips that one check when it is absent.

Targeted Phase 3.1 verification:

```powershell
./_source/.venv/Scripts/python.exe -m pytest tests/chaos -q
```

Last observed result:

```text
9 passed in 1.20s
```

Targeted Phase 3.2 evidence verification:

```powershell
./_source/.venv/Scripts/python.exe -m pytest tests/unit/test_phase32_readiness.py -q
```

Last observed result:

```text
5 passed, 1 warning in 0.34s
```

Targeted Phase 3.3 evidence verification:

```powershell
./_source/.venv/Scripts/python.exe -m pytest tests/unit/test_phase33_readiness.py -q
```

Last observed result:

```text
4 passed, 1 warning in 0.46s
```

Targeted Phase 3.4 evidence verification:

```powershell
./_source/.venv/Scripts/python.exe -m pytest tests/unit/test_phase34_go_live.py -q
```

Last observed result:

```text
5 passed in 0.35s
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

The safe broker contract layer now covers `PaperBroker`. The Dhan gateway side of that
contract remains intentionally absent until the operator explicitly approves an HTTP-mocked
DhanGateway implementation; no live Dhan order path exists in this checkout.

Phase 2's repository code is implemented, but G2's network assertions still require
environment-side proof on the Oracle/Tailscale host:

- Dashboard fill reflection is covered locally through the SSE/snapshot path; verify
  <=3 seconds on the deployed paper host once Oracle is provisioned.
- Dashboard kill switch is covered locally and blocks submission in under 1 second; repeat
  the timed check from phone/laptop over Tailscale.
- Prove off-tailnet refusal with a port scan once the host exists.
- Keep the postback endpoint disabled until the HMAC secret and isolated public ingress are
  reviewed.

Phase 3.1's repository failure-injection suite and Phase 3.2/3.3/3.4 evidence evaluators
are implemented locally. The `docs/BUILD_PLAN.md` wording also says the chaos suite runs on
the Oracle dev host, Phase 3.2 burn-in runs on live market data, Phase 3.3 paper validation
runs on the paid live host, and Phase 3.4 requires the go-live checklist evidence before the
10% live stage; that environment-side execution is still pending until the Oracle/Tailscale
paper host and paid live host are provisioned and operated through the required calendar
periods.

## Git / Workspace Notes

The root `D:\XOLVER\XenAlgo` directory is now initialized as the XenAlgo Git repository.
`_source/` remains a separate local cloned research snapshot in the operator checkout, but
it is no longer represented as a Git submodule because the upstream snapshot URL is not
available to GitHub Actions. Do not commit `_source/`, `_source/.venv/`, `.env`,
`*.duckdb`, `Diary/`, `Supply/`, or secret material.

## Generated Artifacts

Running the promoted research tests from repo root can create transient `Lab/` and `Diary/`
folders. They are ignored by `.gitignore`; remove them after verification if they appear.

## Next Safe Step

Provision the Oracle/Tailscale paper host from `docs/PHASE0_OPERATIONS.md`, run the Phase 2
console there with `XENALGO_CONSOLE_TOKEN` and `TAILSCALE_BIND_HOST`, and capture G2 network
evidence. Then run the now-complete Phase 3.1 chaos suite on that host and attach the host
evidence before starting the 4-week paper burn-in. During burn-in, collect the CSV evidence
described in `docs/PHASE3_2_OPERATIONS.md` and evaluate it with `BurnInReview`. After paid
live-host migration, collect the post-migration CSV evidence described in
`docs/PHASE3_3_OPERATIONS.md` and evaluate it with `PostMigrationValidationReview`. Then
collect the Phase 3.4 go-live checklist evidence described in
`docs/PHASE3_4_OPERATIONS.md` and evaluate it with `GoLiveChecklistReview`. Do not introduce
a live Dhan order path without a separate, explicit operator request.
