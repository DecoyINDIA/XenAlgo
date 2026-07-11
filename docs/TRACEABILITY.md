# Requirements and Safety Traceability

This matrix is the B0 authoritative PRD -> component -> invariant -> executable-spec map.

| Requirement | Component | Safety invariant(s) | Primary executable specs |
|---|---|---|---|
| FR-1 | `TokenManager`, `FyersOAuthProvider` | SI-6 | `test_commissioning_c_to_g.py`, `test_failure_injection.py` |
| FR-2 | scheduler, production paper daemon | SI-6, SI-11 | `test_scheduler_and_killswitch.py`, `test_production_paper_daemon.py` |
| FR-3 | `DataService`, Fyers history loader | SI-6 | `test_reconciler_and_data.py`, `test_commissioning_c_to_g.py` |
| FR-4/FR-5 | sleeve allocator and netting | SI-2, SI-4 | `test_sleeves_and_idempotency.py`, `test_production_paper_daemon.py` |
| FR-6/FR-16 | execution engine and journal | SI-3, SI-4, SI-9 | `test_order_state_machine.py`, `test_execution_phase_a.py` |
| FR-7 | injected Fyers gateway and governor | SI-1, SI-5, SI-12 | `test_broker_contract.py`, `test_governor.py` |
| FR-8 | Order WS adapter, REST poller, fill listener | SI-3, SI-4, SI-9 | `test_fyers_operational_adapters.py`, `test_failure_injection.py` |
| FR-9/FR-10/FR-19 | `RiskEngine` | SI-1, SI-2, SI-4, SI-6, SI-7 | `test_risk_engine.py` |
| FR-11 | reconciler | SI-8 | `test_reconciler_and_data.py`, `test_production_paper_daemon.py` |
| FR-12 | kill switch | SI-10 | `test_scheduler_and_killswitch.py`, `test_phase2_console.py` |
| FR-13 | concrete `PaperBroker` composition | SI-3, SI-4, SI-5, SI-8 | `test_phase1_paper_day.py`, `test_production_paper_daemon.py` |
| FR-14/FR-15 | alerts and private console | SI-10 | `test_phase2_console.py`, `test_commissioning_c_to_g.py` |
| FR-17 | session evidence and phase evaluators | SI-6, SI-8, SI-9 | `test_phase32_readiness.py`, `test_phase33_readiness.py` |
| FR-18 | config checksum and deploy guard | SI-11 | `test_phase0_scaffold.py`, `test_scheduler_and_killswitch.py` |

Every SI-1 through SI-12 has at least one primary executable specification. Changes to a
mapped component must update this matrix and its test docstring in the same change.
