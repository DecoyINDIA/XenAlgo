# XenAlgo — Documentation Set

Read in this order:

0. **[AGENTS.md](../AGENTS.md)** — operating guide for AI agents: prime directives, repo layout, commands, safety rules. Read first if you are an agent editing this repo.
1. **[PLAN.md](../PLAN.md)** — master plan: architecture, guardrail stack, roadmap, decisions.
2. **[PRD.md](PRD.md)** — product requirements: goals, personas, user stories, functional/non-functional requirements.
3. **[TRD.md](TRD.md)** — technical requirements: component specs, data model, interfaces, config, security.
4. **[BUILD_PLAN.md](BUILD_PLAN.md)** — phased build with per-phase exit gates.
5. **[SUCCESS_CRITERIA.md](SUCCESS_CRITERIA.md)** — measurable gates, safety invariants (SI-1..SI-12), quality metrics.
6. **[TEST_PLAN.md](TEST_PLAN.md)** — test strategy; specs live in `../tests/`.

## Traceability chain
PRD goal → FR requirement → TRD component → build-plan task → success criterion / safety invariant → test.

## Test suite
- `tests/unit/` — executable specs for risk, order-state-machine, governor, reconciler, data gates, sleeves, scheduler, kill switch. These now run against the Phase 1 implementation.
- `tests/chaos/` — failure-injection suite (Phase 3.1 go-live blocker).
- `_source/Lab/` — existing research-engine tests (4 passing).

Run: `pytest` (from repo root). Safety-invariant regressions are unconditional release blockers.
