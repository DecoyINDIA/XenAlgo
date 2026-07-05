# XenAlgo — Test Plan

**Version:** 1.0 · **Date:** 2026-07-04

## 1. Philosophy
Safety-critical code is written **test-first**. The unit tests in `tests/unit/` are *executable specifications*: they encode the contracts from `TRD.md` and the invariants from `SUCCESS_CRITERIA.md`. Until a `xenalgo.*` module exists, its test module skips cleanly (`pytest.importorskip`), so the suite is always green and each spec "lights up" the moment its implementation lands.

## 2. Test Layers
| Layer | Scope | Tools | Where |
|---|---|---|---|
| Unit | Pure logic per component (risk checks, state machine, governor, sizing, freshness). | pytest, hypothesis | `tests/unit/` |
| Contract | `BrokerInterface` implementations (Dhan + Paper) obey the same contract via a shared test. | pytest, respx (HTTP mock) | `tests/contract/` |
| Integration | Monolith wiring: startup gate, a full paper day, reconciliation loop. | pytest-asyncio | `tests/integration/` |
| Failure-injection | Adversarial: crash mid-order, WS drop, token expiry, bad candle, rejection storm. | pytest + fault harness | `tests/chaos/` |
| Property | Invariants hold over randomized inputs (fills, restarts, event streams). | hypothesis | `tests/unit/` (marked) |

## 3. Coverage Targets
- Overall ≥90%; **100%** on `xenalgo/risk/` and `xenalgo/execution/`.
- Every SI-1..SI-12 invariant has ≥1 dedicated test (mapping in each test file's docstring).

## 4. Fixtures & Doubles
- `FakeClock` — deterministic IST time control for scheduler/window/token tests.
- `MockBroker` — in-memory `BrokerInterface` with programmable acks/fills/rejections/latency.
- `respx` — mock Dhan REST at the HTTP layer for `DhanGateway` tests (no live calls, ever).
- `tmp_journal` — a throwaway SQLite WAL DB per test.
- `synthetic_panel` — reuse existing test panel builders from `Lab/test_platform.py`.
- **No test ever touches the real Dhan API or places a real order.**

## 5. CI Policy
- Full unit+contract+integration suite on every change; chaos suite nightly and pre-gate.
- A failing **safety invariant** test blocks merge unconditionally.
- Coverage gate enforced on `risk/` and `execution/`.

## 6. Traceability (test ⇄ requirement)
Each test module header lists the SI-/FR- IDs it covers. The go-live checklist requires every SI-1..SI-12 to map to ≥1 green test.
