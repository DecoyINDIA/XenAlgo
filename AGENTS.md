# AGENTS.md — Operating Guide for AI Agents in XenAlgo

This file is the contract for any AI agent (Claude Code, Cursor, etc.) working in this
repository. Read it fully before editing. **XenAlgo trades real money on the NSE via the
Fyers broker API.** A bug here is not a failing test — it is a financial loss. Behave
accordingly: conservative, verified, reversible.

---

## 0. The Prime Directives (never violate)

1. **Never place, modify, or cancel a real order from a dev/test context.** No agent action
   may call the live Fyers order API. Tests use `MockBroker`/`PaperBroker` only. There is no
   "quick live check."
2. **The RiskEngine is a pure veto layer. Never let strategy or execution code bypass it.**
   Every order flows through `RiskEngine.check()`. Do not add a code path that skips it.
3. **Positions change only from confirmed fills.** Never mutate positions on a `PENDING`/
   `SUBMITTED`/`ACCEPTED` state. Only a confirmed fill event does. (This was the original
   cloned code's core bug — do not reintroduce it.)
4. **The order journal (`order_events`) is append-only.** Never `UPDATE` or `DELETE` it.
   Current state is *derived* by replay.
5. **Never weaken a safety invariant (SI-1..SI-12) to make a test pass.** If a change
   trips a safety test, the change is wrong, not the test. Safety-test regressions are
   unconditional blockers.
6. **Never commit secrets.** No `client_id`, PIN, TOTP secret, tokens, or `.env` contents
   in code, logs, tests, or commits. Access tokens are ephemeral and never persisted to git
   or backups.
7. **Do not "improve" the three strategies** (`std30`, `alpha_027`, `alpha_062`) or the
   `Brain/` research engine unless explicitly asked. Their edge is validated on real Fyers
   data; silent changes invalidate that.
8. **When unsure about anything touching orders, risk, money, or compliance — stop and ask.**
   Do not guess in this domain.

---

## 1. What This Project Is

A fully autonomous, single-user swing-trading system for NSE equities via Fyers. It runs
three validated alpha strategies as independent capital sleeves, wraps them in an
institutional-grade guardrail stack, executes with zero human intervention in the loop, and
exposes a secure real-time console for supervision and override. Phase 4 adds a learning
layer. Full intent is in `PLAN.md`; do not restate it, build to it.

**Read these before non-trivial work** (in order):
`PLAN.md` → `docs/PRD.md` → `docs/TRD.md` → `docs/BUILD_PLAN.md` →
`docs/SUCCESS_CRITERIA.md` → `docs/TEST_PLAN.md`.

The traceability chain is: PRD goal → FR requirement → TRD component → build task →
success criterion / safety invariant → test. Keep it intact when you add anything.

---

## 2. Repository Layout

```
XenAlgo/
├── PLAN.md                 # master plan (source of truth for design decisions)
├── AGENTS.md               # this file
├── pytest.ini              # test config (testpaths = tests)
├── docs/                   # PRD, TRD, BUILD_PLAN, SUCCESS_CRITERIA, TEST_PLAN, README
├── tests/                  # executable specs for Phase 0/1 plus chaos scenarios
│   ├── conftest.py         # FakeClock, MockBroker, tmp_journal, fixtures
│   ├── unit/               # risk, state machine, governor, reconciler, sleeves, scheduler
│   └── chaos/              # failure-injection suite (Phase 3.1 go-live blocker)
├── Brain/                  # promoted research/backtest engine (kept byte-identical where tested)
├── Strategies/             # promoted validated strategies
├── _source/                # original cloned quant-swing-trade snapshot
│   ├── Brain/              # data_manager, alpha_engine, portfolio_engine, backtest_engine…
│   ├── Strategies/         # the 3 alphas (plug-and-play)
│   ├── Lab/                # existing research tests (4 passing)
│   ├── Settings/config.yaml
│   └── .venv/              # Python 3.14 venv with deps installed
└── xenalgo/                # Phase 1 paper execution system
```

**Phase status: Phase 1 paper execution core implemented.** The root `xenalgo/` package now
contains risk, execution, governor, paper broker, token, data, scheduler, strategy, ops, alert,
reconciliation, and paper-day orchestration modules. The Phase 1 specs run in the root suite
and must remain green. `_source/` remains as the original cloned snapshot and still has its
own research tests.

---

## 3. Environment & Commands

- **Python:** 3.14 (via uv). Venv at `_source/.venv/`.
- **OS:** Windows. Shell is PowerShell primary; a Bash tool is available. Use `./_source/.venv/Scripts/python.exe`.

**Run the agent-facing spec suite** (from repo root):
```
./_source/.venv/Scripts/python.exe -m pytest -q
```
Expect: Phase 0/1 specs and the current chaos subset to pass. Phase 1 modules no longer skip.

**Run the existing research-engine tests** (from `_source/`, which has `Brain/` on path):
```
cd _source && ./.venv/Scripts/python.exe -m pytest Lab/ -q      # 4 passing
```

**Run the research pipeline end-to-end** (synthetic data if no Dhan keys configured):
```
cd _source && ./.venv/Scripts/python.exe main.py download   # → run → report
```

**Chaos suite** is marked `@pytest.mark.chaos` — runs nightly/pre-gate, not on every change:
```
./_source/.venv/Scripts/python.exe -m pytest -m chaos
```

---

## 4. Coding Conventions

- **Match the surrounding code.** The `Brain/` engine is vectorized pandas with module-level
  loggers named `"QuantPlatform.<Component>"`. New `xenalgo/` code follows the TRD component
  layout and interface sketches in `docs/TRD.md` §2/§4. Note that `xenalgo.execution` is the
  only sanctioned execution path; `Brain`'s executor is research-only.
- **Typed, pure where it matters.** `RiskEngine.check()` is pure (no I/O, no mutation of
  inputs) — there is a test asserting this. Keep risk logic pure and unit-testable.
- **Async for I/O.** Broker/network/DB I/O is asyncio (`httpx.AsyncClient`, `websockets`).
  Strategy math stays synchronous pandas.
- **One writer for DuckDB.** In the live process DuckDB is opened **read-only**; only the
  nightly ingest task writes. Do not open a second writer.
- **SQLite journal:** WAL mode, `synchronous=FULL`. Every order-affecting change is written
  write-ahead (intent before the API call) and applied idempotently.
- **Determinism in orders:** every order carries a deterministic `correlationId`. Reuse it
  for idempotent lookup (`/orders/external/{cid}`) before any resubmit. Never blind-retry a POST.
- **`ponytail:` comments** mark deliberate shortcuts/deferrals — keep the convention; don't
  silently "fix" them without checking intent.
- **Pin dependencies exactly** for anything the live system relies on (e.g. `fyers-apiv3` —
  refer to the external-injected boundary described in `config.py`).

---

## 5. Testing Rules

- **Test-first for safety-critical code** (`xenalgo/risk/`, `xenalgo/execution/`): the spec
  already exists in `tests/`; implement to satisfy it. Target **100% coverage** there.
- Every safety invariant SI-1..SI-12 (`docs/SUCCESS_CRITERIA.md` §2) maps to ≥1 test. If you
  add a control, add its test and cite the SI-/FR- id in the test docstring.
- **No test may touch the real Fyers API or place a real order** — ever. Use `MockBroker`
  (`tests/conftest.py`) and `respx` for HTTP-level mocking.
- Keep the root suite green: unimplemented modules must SKIP, not ERROR.

---

## 6. Hard External Constraints (compliance — do not design around these, design *within* them)

- **SEBI 10 orders/sec threshold:** stay far below it. The governor hard-caps at 2 OPS. Never
  add anything that could exceed it. (Below 10 OPS on your own account = no exchange algo
  registration needed; that relief depends on staying under.)
- **Static IP with a 7-day change lock:** the order API requires a registered static IP.
  Changing it locks for 7 days. Never assume infra/IP can change on short notice near go-live.
- **24h Fyers token:** refreshed pre-market. If a task needs a valid token, go through
  `TokenManager.ensure_valid()`; never hardcode or cache a token in code.
- **Hosting is two-stage:** Oracle Cloud Always Free (dev/paper) → paid Mumbai VPS (live).
  Keep the app Docker-portable so migration is a redeploy, not a rewrite.

---

## 7. Git & Change Discipline

- This directory is **a git repo on `main`**. Do not force-push or commit config yaml files or secrets.
- Never commit `_source/.venv/`, `.env`, `*.duckdb`, `Diary/`, `Supply/`, or any secret.
- Prefer small, reviewable changes. When you change a design decision, update `PLAN.md` and
  the affected doc(s) in the same change so the doc set stays consistent — the docs are
  load-bearing, not decoration.
- **No deploy/config change is ever done "during market hours"** — this is a system rule
  enforced in code (Knight Capital lesson); respect it in tooling too.

---

## 8. When Working on Behalf of the Operator

The operator (single owner, real capital) values: correctness over cleverness, guardrails
over features, honesty over optimism. Report failures plainly with evidence. Never claim
something is verified unless you ran it. If a task would touch real money, external services,
or compliance boundaries, confirm before acting — approval in one context does not carry to
the next.
