# XenAlgo — Documentation Set

Read in this order:

0. **[AGENTS.md](../AGENTS.md)** — operating guide for AI agents: prime directives, repo layout, commands, safety rules. Read first if you are an agent editing this repo.
1. **[PLAN.md](../PLAN.md)** — master plan: architecture, guardrail stack, roadmap, decisions.
2. **[PRD.md](PRD.md)** — product requirements: goals, personas, user stories, functional/non-functional requirements.
3. **[TRD.md](TRD.md)** — technical requirements: component specs, data model, interfaces, config, security.
4. **[BUILD_PLAN.md](BUILD_PLAN.md)** — phased build with per-phase exit gates.
5. **[SUCCESS_CRITERIA.md](SUCCESS_CRITERIA.md)** — measurable gates, safety invariants (SI-1..SI-12), quality metrics.
6. **[TEST_PLAN.md](TEST_PLAN.md)** — test strategy; specs live in `../tests/`.
7. **[PHASE3_2_OPERATIONS.md](PHASE3_2_OPERATIONS.md)** — burn-in and live-host evidence runbook.
8. **[PHASE3_3_OPERATIONS.md](PHASE3_3_OPERATIONS.md)** — post-migration paper-validation evidence runbook.
9. **[PHASE3_4_OPERATIONS.md](PHASE3_4_OPERATIONS.md)** — go-live checklist evidence runbook for the 10% live-capital stage.

## Traceability chain
PRD goal → FR requirement → TRD component → build-plan task → success criterion / safety invariant → test.

## Test suite
- `tests/unit/` — executable specs for risk, order-state-machine, governor, reconciler, data gates, sleeves, scheduler, kill switch. These now run against the Phase 1 implementation.
- `tests/unit/test_phase32_readiness.py` — Phase 3.2 evidence-gate checks for burn-in and live-host readiness.
- `tests/unit/test_phase33_readiness.py` — Phase 3.3 evidence-gate checks for post-migration paper validation on the live host.
- `tests/unit/test_phase34_go_live.py` — Phase 3.4 evidence-gate checks for the go-live checklist and 10% activation boundary.
- `tests/integration/` — paper-day orchestration and Phase 2 console/SSE/control-path integration tests.
- `tests/chaos/` — failure-injection suite (Phase 3.1 go-live blocker).
- `_source/Lab/` — optional local research-engine tests when the operator snapshot is present.

Run from repo root: `./_source/.venv/Scripts/python.exe -m pytest -q` in the operator checkout, or `python -m pytest -q` in CI after installing `requirements.lock`. Safety-invariant regressions are unconditional release blockers.
