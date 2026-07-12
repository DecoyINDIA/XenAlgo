# XenAlgo Deployment Status

**Recorded:** 2026-07-12

**Governing plan:** [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)

**Safety state:** paper mode; `live_trading.enabled=false`; `broker.order_api_enabled=false`.

## Current gate ledger

| Gate | Status | Evidence or next required event |
|---|---|---|
| D0 release acceptance | Complete for Oracle paper | Release `bbdb5ff`, green CI run `29164737124`, exact candidate and rollback identities, and operator paper-deployment approval are recorded privately. The host-control fix following deployment requires a superseding release candidate. |
| D1 Oracle readiness | Partial on host | Oracle Linux 9.7 in Mumbai, NTP, Docker, Tailscale-only console/SSH, public port refusal, local monitoring, backup timer, and verified off-box pull are proven. External heartbeat and real-phone alert delivery remain missing. |
| D2 Oracle paper deployment | Partial on host | Exact `bbdb5ff` image deployed. Kill blocked in 28 ms, restart recovered in 8.744 s, journal/restore integrity passed, and no duplicate intent/order appeared. Fyers credentials, runnable scheduled daemon preflight, heartbeat, and synthetic alert delivery remain missing. |
| D3 five-session commissioning | Calendar-bound | Requires five consecutive expected NSE sessions on Oracle; synthetic evidence is rejected. |
| D4 paid-host provisioning | Operator/external | Provider, account/capital, current broker network requirements, host, alerts, and restore must be selected and proven. |
| D5 paid-host parity | External host-bound | Exact commissioned image/config must pass focused parity in paper/read-only mode. |
| D6 final go-live review | Operator/external | Requires D3/D5 plus all checklist evidence; pre-activation flags remain false. |
| D7 explicit 10% activation | Separate approval required | No approval supplied. This work does not authorize or perform activation. |
| D8 staged ramp | Elapsed-time/real-capital bound | Four explicit stages, each at least two calendar weeks and ten reviewed sessions. |
| D9 G3 handoff | Dependent on D8 | Handoff completeness gate is ready; it cannot pass before the 100% clean window finishes. |

## Verified local release checks

- Root suite: 163 passed.
- XenAlgo coverage: 90.24% (required minimum 90%).
- `xenalgo.risk` plus `xenalgo.execution`: 100%.
- Research suite: 4 passed.
- Research and live configuration validation: passed; live checksum
  `8020b612358e6da269c1964211bb07b524b27450afee35b1b7130a69be407500`.
- Docker build and containerized live-profile smoke: passed locally.
- Tracked secret-assignment pattern scan: no populated secret assignment found.
- `git diff --check`: passed.

These local proofs are supplemented by private host evidence under `Diary/deployment/`.
They are not commissioning, paid-host parity, broker readiness, or live-capital proof.

## Operator sequence

1. Review and commit the intended release; obtain clean CI and immutable image digest.
2. Fill private D0 evidence and approve Oracle paper deployment only.
3. Run Oracle bootstrap outside market hours, finish Tailscale/alerts/off-box backup, collect
   and validate D1 evidence.
4. Execute D2 paper smoke/restart/restore checks without any real order call.
5. Collect five consecutive authoritative D3 sessions.
6. Provision and validate D4/D5, then conduct D6 review.
7. Stop for a separate explicit D7 approval. D8/D9 advance only from observed evidence.
