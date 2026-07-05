# XenAlgo Handoff

**Last updated:** 2026-07-05  
**Current phase:** Phase 1 paper execution core implemented; Phase 2 console not started.  
**Working directory:** `D:\XOLVER\XenAlgo`

## Safety Posture

XenAlgo is a real-money NSE trading system design. No live Dhan order API path was called,
tested, or enabled during Phase 1. The live config keeps both `live_trading.enabled` and
`broker.order_api_enabled` set to `false`; the implemented end-to-end path is paper-mode only.

Phase 1 executable specs now run rather than skip. `ExecutionEngine.submit()` calls
`RiskEngine.check()` before broker submission, and idempotency still adopts an existing
correlation id instead of re-posting an order.

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

## Verification Evidence

Run from repo root:

```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
```

Last observed result:

```text
73 passed
```

Run from `_source`:

```powershell
./.venv/Scripts/python.exe -m pytest Lab/ -q
```

Last observed result:

```text
4 passed
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

Follow `docs/PHASE0_OPERATIONS.md` for the checklist.

## Phase 1 Limitations / Next Engineering Boundary

The paper-mode core is implemented and tested locally. The production Dhan REST/WebSocket
gateway is still intentionally not live-enabled in this checkout; before any real broker
integration, keep `broker.order_api_enabled=false`, use HTTP-level mocks only, and require an
explicit operator approval for any change that could touch real orders. Phase 2 should start
with the FastAPI/HTMX console, SSE state feed, kill-switch endpoint, and authenticated breaker
re-arm flow.

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

Start Phase 2 only after re-reading `PLAN.md`, `docs/PRD.md`, `docs/TRD.md`,
`docs/BUILD_PLAN.md`, `docs/SUCCESS_CRITERIA.md`, and `docs/TEST_PLAN.md`. Build the console
against the paper-mode state surfaces first; do not introduce a live Dhan order path without a
separate, explicit operator request.
