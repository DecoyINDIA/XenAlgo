# XenAlgo Deployment Status

**Recorded:** 2026-07-14

**Governing plan:** [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)

**Operator inputs:** [DEPLOYMENT_OPERATOR_INPUTS.md](DEPLOYMENT_OPERATOR_INPUTS.md)

**Safety state:** paper mode; `live_trading.enabled=false`; `broker.order_api_enabled=false`.

## Current gate ledger

| Gate | Status | Evidence or next required event |
|---|---|---|
| D0 release acceptance | Complete for Oracle paper | The current release has green CI, exact candidate/rollback identities, and recorded operator paper-deployment approval. Private evidence is updated on every superseding release. |
| D1 Oracle readiness | Complete | Oracle Linux 9.7 in Mumbai, NTP, Docker, Tailscale-only console/SSH, public port refusal, monitoring, backup timer, verified off-box pull, a one-minute external heartbeat, and a missed-heartbeat Telegram delivery to the operator are proven. |
| D2 Oracle paper deployment | Runtime controls complete; release identity pending | Fyers authentication is valid in the owner-only token volume. The paper service now runs a fail-closed preflight at startup and from an enabled 08:55 IST systemd timer. The first scheduled run passed authentication, calendar, config, journal replay, completed-bar Fyers data, controls, reconciliation, concrete `PaperBroker`, and synthetic Healthchecks application-event delivery with zero order-API calls. Kill/restart/restore evidence remains green. The new image must still pass a superseding D0 immutable-release acceptance before D2 can honestly pass its image-identity check. |
| D3 five-session commissioning | Calendar-bound | Requires five consecutive expected NSE sessions on Oracle; synthetic evidence is rejected. |
| D4 Oracle production readiness | External host-bound | Exact commissioned image/config must pass focused same-host parity in paper/read-only mode. Oracle remains the permanent host. |
| D5 final go-live review | Operator/external | Requires D3/D4 plus all checklist evidence; pre-activation flags remain false. |
| D6 explicit 10% activation | Separate approval required | No approval supplied. This work does not authorize or perform activation. |
| D7 staged ramp | Elapsed-time/real-capital bound | Four explicit stages, each at least two calendar weeks and ten reviewed sessions. |
| D8 G3 handoff | Dependent on D7 | Handoff completeness gate is ready; it cannot pass before the 100% clean window finishes. |

## Verified local release checks

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

1. Review and commit the intended release; obtain clean CI and immutable image digest.
2. Fill private D0 evidence and approve Oracle paper deployment only.
3. Run Oracle bootstrap outside market hours, finish Tailscale/alerts/off-box backup, collect
   and validate D1 evidence.
4. Execute D2 paper smoke/restart/restore checks without any real order call.
5. Collect five consecutive authoritative D3 sessions.
6. Validate D4 on Oracle, then conduct the D5 review.
7. Stop for a separate explicit D6 approval. D7/D8 advance only from observed evidence.
