# XenAlgo — Documentation Set

Read in this order:

0. **[AGENTS.md](../AGENTS.md)** — agent safety contract and repository commands.
1. **[PLAN.md](../PLAN.md)** — master architecture, guardrails, roadmap, and decisions.
2. **[PRD.md](PRD.md)** — product and functional requirements.
3. **[TRD.md](TRD.md)** — components, interfaces, data model, configuration, and security.
4. **[BUILD_PLAN.md](BUILD_PLAN.md)** — phased build and exit gates.
5. **[SUCCESS_CRITERIA.md](SUCCESS_CRITERIA.md)** — measurable gates and SI-1 through SI-12.
6. **[TEST_PLAN.md](TEST_PLAN.md)** — test strategy and release policy.
7. **[FYERS_CONTRACT.md](FYERS_CONTRACT.md)** — source-backed Fyers v3 contract and B0 decisions.
8. **[TRACEABILITY.md](TRACEABILITY.md)** — FR/component/SI/executable-test mapping.
9. **[PHASE3_2_OPERATIONS.md](PHASE3_2_OPERATIONS.md)** — five-session software-commissioning runbook.
10. **[PHASE3_3_OPERATIONS.md](PHASE3_3_OPERATIONS.md)** — focused paid-host deployment-parity runbook.
11. **[PHASE3_4_OPERATIONS.md](PHASE3_4_OPERATIONS.md)** — 10% go-live checklist evidence.
12. **[PHASE3_5_OPERATIONS.md](PHASE3_5_OPERATIONS.md)** — staged capital-ramp evidence.
13. **[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)** — Oracle, commissioning, paid-host, rollback, and activation gates.
14. **[HANDOFF.md](HANDOFF.md)** — completed B0-B6 release identity, verification, startup, rollback, and external boundaries.
15. **[RESEARCH_VALIDATION.md](RESEARCH_VALIDATION.md)** — offline walk-forward validation harness.
16. **[FOUNDER_PITCH.md](FOUNDER_PITCH.md)** — layperson-oriented product and safety overview.

## Authoritative completion plans

- **[END_TO_END_COMPLETION_PLAN.md](END_TO_END_COMPLETION_PLAN.md)** defines the full sequence from contract freeze through external deployment and operations.
- **[PHASED_BUILD_PLAN_REMAINING.md](PHASED_BUILD_PLAN_REMAINING.md)** records Engineering phases B0-B6 and their completed local proof.
- **[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)** defines D0-D9. Local tests cannot replace host, broker, operator, or calendar-time evidence.

## Traceability chain

PRD goal → FR requirement → TRD component → build task → success criterion / safety invariant → executable test.

## Current test surfaces

- `tests/unit/` — risk, state machine, governor, reconciliation, data, sleeves, scheduling, kill switch, and phase evaluators.
- `tests/unit/test_phase32_readiness.py` — five-consecutive-session software-commissioning gate.
- `tests/unit/test_phase33_readiness.py` — focused deployment-parity gate; no second strategy-duration test.
- `tests/unit/test_phase34_go_live.py` — pre-activation and 10% activation evidence boundary.
- `tests/unit/test_phase35_capital_ramp.py` — 10% → 25% → 50% → 100% capital-ramp evidence.
- `tests/contract/` — paper and injected/mock-only Fyers contracts.
- `tests/integration/` — paper day, production scheduled session, recovery/idempotency, evidence, console, SSE, and control paths.
- `tests/chaos/` — failure injection and 1,000-iteration replay proof.
- `_source/Lab/` — promoted research-engine tests.

Run from the repository root:

```powershell
./_source/.venv/Scripts/python.exe -m pytest -q --basetemp .tmp/pytest
```

Safety-invariant regressions are unconditional release blockers.
