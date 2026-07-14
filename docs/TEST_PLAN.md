# XenAlgo — Test Plan

**Version:** 1.0 · **Date:** 2026-07-04

## 1. Philosophy
Safety-critical code is written **test-first**. The unit tests in `tests/unit/` are *executable specifications*: they encode the contracts from `TRD.md` and the invariants from `SUCCESS_CRITERIA.md`. Until a `xenalgo.*` module exists, its test module skips cleanly (`pytest.importorskip`), so the suite is always green and each spec "lights up" the moment its implementation lands.

## 2. Test Layers
| Layer | Scope | Tools | Where |
|---|---|---|---|
| Unit | Pure logic per component (risk checks, state machine, governor, sizing, freshness, Phase 3.2/3.3/3.4/3.5 evidence gates). | pytest, hypothesis | `tests/unit/` |
| Contract | `BrokerInterface` implementations obey the same contract. PaperBroker is active now; FyersGateway coverage uses injected/mocked clients only. | pytest, respx (HTTP mock) | `tests/contract/` |
| Integration | Monolith wiring: startup gate, a full paper day, reconciliation loop. | pytest-asyncio | `tests/integration/` |
| Failure-injection | Adversarial: crash mid-order, WS drop, token expiry, bad candle, rejection storm. | pytest + fault harness | `tests/chaos/` |
| Property | Invariants hold over randomized inputs (fills, restarts, event streams). | hypothesis | `tests/unit/` (marked) |

## 3. Coverage Targets
- Overall ≥90%; **100%** on `xenalgo/risk/` and `xenalgo/execution/`.
- Every SI-1..SI-12 invariant has ≥1 dedicated test (mapping in each test file's docstring).

## 4. Fixtures & Doubles
- `FakeClock` — deterministic IST time control for scheduler/window/token tests.
- `MockBroker` — in-memory `BrokerInterface` with programmable acks/fills/rejections/latency.
- `respx` / injected clients — mock Fyers REST/SDK behavior (no live calls, ever).
- `tmp_journal` — a throwaway SQLite WAL DB per test.
- `synthetic_panel` — use repo-local builders; the optional `_source/Lab` tests can still be run in the operator checkout.
- **No test ever touches the real Fyers API or places a real order.**
- Current live gateway coverage is mock-only; live-order-capable enablement remains outside the current safe boundary.
- Phase 3.2 tests validate operator-supplied evidence only. They do not provision hosts,
  register static IPs, call Fyers, or enable live trading.
- Phase 3.3 tests validate operator-supplied same-host production-readiness evidence only. They do not
  operate the Oracle host, call Fyers, or enable live trading.
- The owner revised the paper gate on 2026-07-11: Phase 3.2 is one software commissioning
  week with at least five consecutive NSE sessions, and Phase 3.3 is focused deployment
  parity. The evaluator implementations and tests encode those current decisions. Strategy
  return deviation is recorded for observation but is not a one-week software pass gate.
- Phase 3.4 tests validate operator-supplied go-live checklist evidence only. They do not
  call Fyers, fund accounts, mutate config, or place live orders.
- Phase 3.5 tests validate operator-supplied staged-ramp evidence only. They do not call
  Fyers, advance capital, mutate config, or place live orders.

## 5. CI Policy
- Full committed repo suite on every change; chaos suite nightly and pre-gate. Optional `_source/Lab` research tests are run separately when that local snapshot exists.
- A failing **safety invariant** test blocks merge unconditionally.
- Coverage gate enforced on `risk/` and `execution/`.

## 6. Traceability (test ⇄ requirement)
Each test module header lists the SI-/FR- IDs it covers. The go-live checklist requires every SI-1..SI-12 to map to ≥1 green test.
