# XenAlgo Deployment Status

**Recorded:** 2026-07-14

**Governing plan:** [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)

**Operator inputs:** [DEPLOYMENT_OPERATOR_INPUTS.md](DEPLOYMENT_OPERATOR_INPUTS.md)

**Safety state:** paper mode; `live_trading.enabled=false`; `broker.order_api_enabled=false`.

## Current gate ledger

| Gate | Status | Evidence or next required event |
|---|---|---|
| D0 release acceptance | Superseding source accepted; image pending | Commit `b0d7d1cbeec111ca6633ba817f1482dc95a41205` is pushed on `agent/superseding-d0-release`; draft PR #1 targets `main`, both GitHub CI runs passed, local coverage gates passed, and operator approval for the superseding Oracle-paper release is recorded. D0 remains fail-closed until this exact commit is rebuilt after the market-hours lock and its immutable image/rollback identities are written to private evidence. |
| D1 Oracle readiness | Complete | Oracle Linux 9.7 in Mumbai, NTP, Docker, Tailscale-only console/SSH, public port refusal, monitoring, backup timer, verified off-box pull, a one-minute external heartbeat, and a missed-heartbeat Telegram delivery to the operator are proven. |
| D2 Oracle paper deployment | Runtime controls complete; release identity pending | Fyers authentication is valid in the owner-only token volume. The paper service now runs a fail-closed preflight at startup and from an enabled 08:55 IST systemd timer. The first scheduled run passed authentication, calendar, config, journal replay, completed-bar Fyers data, controls, reconciliation, concrete `PaperBroker`, and synthetic Healthchecks application-event delivery with zero order-API calls. Kill/restart/restore evidence remains green. The new image must still pass a superseding D0 immutable-release acceptance before D2 can honestly pass its image-identity check. |
| D3 five-session commissioning | Calendar-bound | Requires five consecutive expected NSE sessions on Oracle; synthetic evidence is rejected. |
| D4 Oracle production readiness | External host-bound | Exact commissioned image/config must pass focused same-host parity in paper/read-only mode. Oracle remains the permanent host. |
| D5 final go-live review | Operator/external | Requires D3/D4 plus all checklist evidence; pre-activation flags remain false. |
| D6 explicit 10% activation | Separate approval required | No approval supplied. This work does not authorize or perform activation. |
| D7 staged ramp | Elapsed-time/real-capital bound | Four explicit stages, each at least two calendar weeks and ten reviewed sessions. |
| D8 G3 handoff | Dependent on D7 | Handoff completeness gate is ready; it cannot pass before the 100% clean window finishes. |

## Verified local release checks

- Superseding release commit: `b0d7d1cbeec111ca6633ba817f1482dc95a41205`.
- Draft review: [PR #1](https://github.com/DecoyINDIA/XenAlgo/pull/1), branch
  `agent/superseding-d0-release`, targeting `main`.
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

1. After the 15:30 IST deployment lock clears, rebuild the Oracle image from exact commit
   `b0d7d1cbeec111ca6633ba817f1482dc95a41205`.
2. Run the paper-only preflight against that image, preserve a rollback image, and record
   the immutable image identity in private D0 evidence.
3. Redeploy through the guarded systemd path; verify the service, 08:55 timer, heartbeat,
   health/SSE, and zero real order calls.
4. Update private D2 identity evidence and require both D0 and D2 evaluators to pass.
5. Collect five consecutive authoritative D3 sessions.
6. Validate D4 on Oracle, then conduct the D5 review.
7. Stop for a separate explicit D6 approval. D7/D8 advance only from observed evidence.
