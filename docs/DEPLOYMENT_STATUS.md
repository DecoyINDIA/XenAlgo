# XenAlgo Deployment Status

**Recorded:** 2026-07-14

**Governing plan:** [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)

**Operator inputs:** [DEPLOYMENT_OPERATOR_INPUTS.md](DEPLOYMENT_OPERATOR_INPUTS.md)

**Safety state:** paper mode; `live_trading.enabled=false`; `broker.order_api_enabled=false`.

## Current gate ledger

| Gate | Status | Evidence or next required event |
|---|---|---|
| D0 release acceptance | Complete | PR #1 is merged. Exact merge commit `f0e6bcaaf7d38f8aa4b61ad1bce73841796632c7` was built and promoted off-market after an isolated paper-only preflight. Its immutable image and rollback identities are recorded in private evidence; the D0 evaluator passes. |
| D1 Oracle readiness | Complete | Oracle Linux 9.7 in Mumbai, NTP, Docker, Tailscale-only console/SSH, public port refusal, monitoring, backup timer, verified off-box pull, a one-minute external heartbeat, and a missed-heartbeat Telegram delivery to the operator are proven. |
| D2 Oracle paper deployment | Complete | The exact D0 image is running on Oracle. Fyers authentication, startup and 08:55 IST scheduled preflight, calendar, journal replay, completed-bar data, controls, reconciliation, concrete `PaperBroker`, synthetic Healthchecks application-event delivery, health, kill/restart/restore, backup, and image/config identity checks pass with zero order-API calls. The D2 evaluator passes. |
| D3 five-session commissioning | Calendar-bound | Requires five consecutive expected NSE sessions on Oracle; synthetic evidence is rejected. |
| D4 Oracle production readiness | External host-bound | Exact commissioned image/config must pass focused same-host parity in paper/read-only mode. Oracle remains the permanent host. |
| D5 final go-live review | Operator/external | Requires D3/D4 plus all checklist evidence; pre-activation flags remain false. |
| D6 explicit 10% activation | Separate approval required | No approval supplied. This work does not authorize or perform activation. |
| D7 staged ramp | Elapsed-time/real-capital bound | Four explicit stages, each at least two calendar weeks and ten reviewed sessions. |
| D8 G3 handoff | Dependent on D7 | Handoff completeness gate is ready; it cannot pass before the 100% clean window finishes. |

## Verified local release checks

- Approved release commit: `f0e6bcaaf7d38f8aa4b61ad1bce73841796632c7`.
- Review: [PR #1](https://github.com/DecoyINDIA/XenAlgo/pull/1), merged to `main`.
- GitHub CI: both push-triggered and pull-request-triggered runs passed.

- Root suite: 172 passed.
- XenAlgo coverage: 90.07% (required minimum 90%).
- `xenalgo.risk` plus `xenalgo.execution`: 100%.
- Research suite: 4 passed.
- Research and live configuration validation: passed; live checksum
  `8020b612358e6da269c1964211bb07b524b27450afee35b1b7130a69be407500`.
- Docker build and containerized live-profile smoke: passed locally.
- Tracked secret-assignment pattern scan: no populated secret assignment found.
- `git diff --check`: passed.

These local proofs are supplemented by private host evidence under `Diary/deployment/`.
They are not commissioning, Oracle production-readiness, broker readiness, or live-capital proof.

## Operator sequence

1. Collect five consecutive authoritative D3 sessions from the exact commissioned image.
2. Validate D4 on Oracle, then conduct the D5 review.
3. Stop for a separate explicit D6 approval. D7/D8 advance only from observed evidence.
