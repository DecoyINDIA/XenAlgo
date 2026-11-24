# XenAlgo

XenAlgo is an autonomous NSE swing-trading system for a single Fyers account. It is built for one practical goal: let the strategies do their job, while the safety layer makes sure nothing reckless reaches the broker.

This is not a signal toy, a broker demo, or a "move fast and break things" trading bot. It is a careful execution system around three already validated NSE equity strategies, with paper trading, risk checks, order journaling, broker reconciliation, and operator control built in from the start.

> Important: when configured for live use, this system can affect real capital. Development and tests must use `MockBroker` or `PaperBroker` only. Do not place, modify, or cancel real Fyers orders from a dev or test context.

## What XenAlgo Does

- Runs three validated swing strategies: `std30`, `alpha_027`, and `alpha_062`.
- Treats each strategy as its own capital sleeve, so performance and exposure stay clear.
- Turns portfolio targets into broker orders through a guarded execution pipeline.
- Sends every order through `RiskEngine.check()` before broker submission.
- Writes order intent and state changes to an append-only SQLite journal.
- Updates positions only after confirmed fills.
- Reconciles local state against Fyers broker truth before and during trading.
- Keeps order rate capped at 2 orders per second, far below the SEBI retail-algo threshold.
- Uses paper execution as the proving ground before live capital is even considered.

## Why It Exists

The trading edge is only useful if execution is trustworthy. XenAlgo focuses on the part that usually causes real damage: bad state, stale data, duplicate orders, missing reconciliation, weak risk controls, and unclear operator visibility.

The design bias is simple:

- Prefer a missed trade over an unsafe trade.
- Prefer a halt over silent drift.
- Prefer replayable facts over mutable assumptions.
- Prefer clear operator control over hidden automation.

## Current Status

The repository-local build is complete through Phase 3.1 failure-injection coverage, with Phase 3.2, Phase 3.3, Phase 3.4, and Phase 3.5 evidence tooling now added. Phase 1 paper execution, Phase 2 operator console surfaces, the deterministic Phase 3.1 chaos suite, Phase 3.2 commissioning/permanent-host readiness checks, Phase 3.3 same-host production checks, Phase 3.4 go-live checklist checks, and Phase 3.5 staged capital-ramp checks are implemented and tested locally.

The repository now includes the paper-only production composition, scheduled job owner,
Fyers live-data/observation adapters, and evaluator-ready commissioning evidence. The
remaining work is external deployment proof: Oracle installation, five consecutive NSE
commissioning sessions, same-Oracle-host production readiness, and separately approved staged live activation.
Commissioning evaluates the software, not one-week profitability. Live Fyers order placement
remains disabled and is outside the B0-B6 authorization boundary.

The root `xenalgo/` package includes broker abstractions, risk, execution, governor, paper broker, token, data, scheduler, strategy, ops, alerting, reconciliation, production paper orchestration, console state, FastAPI/SSE dashboard endpoints, Telegram command routing, and Phase 3.2/3.3/3.4/3.5 evidence evaluation.

The original research and backtest snapshot is kept locally under `_source/` in the operator checkout. It is not required for GitHub Actions because the promoted `Brain/` and `Strategies/` folders preserve the validated research surface in this repository. Strategy logic should not be changed casually.

## Safety Model

XenAlgo is designed around independent checks, not hope:

- **No live order calls in development.** Tests must never touch the real Fyers order API.
- **Risk is a veto layer.** Strategy and execution code do not bypass it.
- **Fills are the source of truth.** Pending, submitted, or accepted orders do not change positions.
- **The order journal is append-only.** Current state is derived by replay.
- **Retries are idempotent.** Every order carries a deterministic `correlationId`.
- **Broker truth wins.** Reconciliation mismatches halt trading and alert the operator.
- **Kill switches are part of the system.** Dashboard, Telegram, and broker-side controls are planned as independent stop paths.

Read [AGENTS.md](AGENTS.md) before editing. It is the operating contract for this repo.

## Repository Map

```text
XenAlgo/
|-- PLAN.md                 # master architecture and roadmap
|-- AGENTS.md               # operating guide for agents and contributors
|-- docs/                   # PRD, TRD, build plan, success gates, test plan
|-- xenalgo/                # paper execution system
|-- tests/                  # unit, integration, and chaos specs
|-- Brain/                  # promoted research and backtest engine
|-- Strategies/             # promoted validated strategies
`-- _source/                # optional local research snapshot and venv
```

## Read First

Start here if you want to understand the project:

1. [PLAN.md](PLAN.md)
2. [docs/PRD.md](docs/PRD.md)
3. [docs/TRD.md](docs/TRD.md)
4. [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md)
5. [docs/SUCCESS_CRITERIA.md](docs/SUCCESS_CRITERIA.md)
6. [docs/TEST_PLAN.md](docs/TEST_PLAN.md)

## Run the Safe Test Suite

Use the pinned Python environment under `_source/.venv/` from PowerShell:

```powershell
./_source/.venv/Scripts/python.exe -m pytest -q
```

Run the original research-engine tests when the optional local `_source/` snapshot is present:

```powershell
cd _source
./.venv/Scripts/python.exe -m pytest Lab/ -q
```

Run chaos tests before a serious gate or release decision:

```powershell
./_source/.venv/Scripts/python.exe -m pytest -m chaos
```

## What "Ready" Means

XenAlgo is not ready because it starts. It is ready only when the safety gates pass:

- Full root test suite green.
- 100% coverage for safety-critical risk and execution behavior.
- Zero duplicate orders across restart simulations.
- No position mutation without confirmed fills.
- Journal replay matches derived state after crash recovery.
- Governor never exceeds 2 orders per second.
- Reconciler halts on injected broker/local drift.
- One commissioning week with at least five consecutive NSE sessions proving the bot's software flow before same-host production-readiness review.
- Focused deployment-parity and startup checks on the paid live host before live capital.

The complete acceptance matrix is in [docs/SUCCESS_CRITERIA.md](docs/SUCCESS_CRITERIA.md).

## Configuration

Copy `.env.example` to a local `.env` only when runtime credentials are needed. Never commit secrets, Fyers tokens, 2FA material, broker IDs, generated databases, or market-data stores.

Live deployment is intentionally gated. Development and software commissioning target Oracle Cloud Always Free. Live capital moves only after the commissioning week, static IP registration, backup drills, deployment-parity checks, and go-live review.

## Contributor Notes

Before changing code:

1. Read [AGENTS.md](AGENTS.md).
2. Find the relevant PRD or TRD requirement.
3. Preserve the safety invariant tied to the change.
4. Add or keep tests for anything touching orders, risk, state, or compliance.
5. Run the relevant tests and report exactly what passed or failed.

If a task touches live orders, broker credentials, capital movement, compliance limits, or market-hours deployment, stop and ask for explicit operator confirmation.

## Use and Disclaimer

This is a single-operator trading system, not a public financial product. Nothing here is financial advice, an invitation to trade, or a recommendation to deploy live capital.
