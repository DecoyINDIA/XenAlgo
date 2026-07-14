# Deployment Operator Inputs and Remaining Gates

**Recorded:** 2026-07-12

**Purpose:** Durable, non-secret handoff for completing D1-D8 on the permanent Oracle host.
This document records names, procedures, and acceptance evidence only. Never add actual
credentials, tokens, phone identifiers, account numbers, IP addresses, or approval secrets.

## Current deployment boundary

- D0 passes for the immutable release recorded in private `Diary/deployment/d0-release.json`.
- The approved image is running on the Oracle Mumbai paper host.
- Public SSH and application ports are refused; administration and console access use
  Tailscale only.
- `live_trading.enabled=false` and `broker.order_api_enabled=false` remain mandatory.
- Kill blocking, restart recovery, journal integrity, and disposable restore are proven
  within D2 limits.
- D1 is complete: Healthchecks receives the one-minute host heartbeat and a controlled
  missed-heartbeat event delivered to the operator through Telegram. D2's host-runtime
  controls are now complete: Fyers authentication, startup and 08:55 IST scheduled
  preflight, read-only completed-bar validation, and synthetic application-event delivery
  through Healthchecks all pass with the concrete paper gateway and zero order-API calls.
  The gate remains fail-closed until the superseding image receives immutable D0 release
  acceptance and the D0/D2 image identities match.

The exact host address, image digest, checksums, approval identifier, and gate JSON remain in
the gitignored `Diary/deployment/` evidence directory.

## Host-local secrets to provision

Edit `/etc/xenalgo/xenalgo.env` directly on the host over Tailscale SSH. Do not paste values
into chat, tickets, documentation, shell history, git, image build arguments, or logs.

Required Fyers values:

| Variable | Purpose | Current evidence |
|---|---|---|
| `FYERS_APP_ID` | Approved Fyers API application identity | Configured; redacted host proof passed |
| `FYERS_SECRET_KEY` | Application secret | Configured; redacted host proof passed |
| `FYERS_REDIRECT_URI` | Exact registered OAuth redirect URI | Configured; redacted host proof passed |
| `FYERS_PIN` | Operator-owned daily authentication input | Missing |
| `FYERS_TOTP_SECRET` | Operator-owned TOTP seed | Missing |
| `XENALGO_STATIC_IP_PRIMARY` | Broker/network identity if required by the approved contract | Missing |
| `XENALGO_STATIC_IP_SECONDARY` | Secondary network identity if required | Missing |

Required operations values:

| Variable | Purpose | Current evidence |
|---|---|---|
| `XENALGO_HEARTBEAT_URL` | Operator-owned external heartbeat endpoint | Configured on Oracle; ping and missed-ping alert proven. |
| `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | Optional direct application-event channel; Healthchecks already owns the proven Telegram integration | Direct credentials not provisioned; Healthchecks event path is active |
| `PUSHOVER_TOKEN` and `PUSHOVER_USER_KEY` | Independent critical phone channel | Missing |

At least the approved alert design in the deployment plan must be proven on the real phone.
Do not mark D1/D2 passed merely because a variable is non-empty; record an observed delivery.

## Safe provisioning procedure

1. Confirm the market is closed and the service is in paper mode.
2. Connect using the private key and the host's current Tailscale address:

   ```powershell
   ssh -i <private-key-path> opc@<tailscale-host-ip>
   ```

3. Edit the root-owned file without printing it:

   ```bash
   sudoedit /etc/xenalgo/xenalgo.env
   sudo chmod 600 /etc/xenalgo/xenalgo.env
   sudo chown root:root /etc/xenalgo/xenalgo.env
   ```

4. Validate names and presence using a redacted checker; never run `cat` on the file in a
   captured terminal.
5. Restart through the normal systemd startup gate only after configuration validation.
6. Confirm the image/config identities still match D0 and both live flags remain false.

## D1 completion evidence

- Healthchecks received the Oracle one-minute health ping.
- The controlled missed-heartbeat drill delivered a Telegram alert to the operator's phone.
- Oracle health timer recovery completed successfully after the drill.
- Private D1 JSON passes `python -m xenalgo.deployment_cli D1 <private-json>`.

Already proven: Oracle Linux/region/host identity, NTP, Docker, systemd, Tailscale health,
tailnet-only binding, public SSH/application refusal, least privilege, monitoring, market-hour
guard, nightly non-secret backup, disposable restore, and scheduled off-box pull.

## Evidence required to close D2

- Fyers authentication and token lifecycle preflight succeeds without logging secrets.
- Calendar, current completed-bar data, restrictions, journal replay, reconciliation, and
  paper-gateway checks pass together.
- The actual scheduled paper daemon and console run under systemd; the console alone is not
  sufficient.
- A mock-only synthetic host event reaches the console and real alert path.
- Heartbeat remains observable through restart and induced recovery.
- Private D2 JSON passes `python -m xenalgo.deployment_cli D2 <private-json>`.

Host-runtime evidence collected 2026-07-14:

- Owner-only Fyers token store: integrity `ok`, mode `0600`, currently valid.
- Read-only Fyers History API returned the latest completed trading-day candle.
- `xenalgo-paper.service` startup preflight passed all checks before the console started.
- `xenalgo-paper-preflight.timer` is enabled and its first 08:55 IST execution exited 0.
- The synthetic `application_event` POST was accepted by the existing Healthchecks channel.
- Both preflight records state `live_order_api_calls=0`.

Remaining D2 blocker: accept the superseding image through D0 and update the private D0
image identity. Do not copy the new image digest into D0 without the required clean release,
CI, checksum, secret-scan, rollback, and operator paper-deployment evidence.

Already proven on the deployed image: immutable identity, paper config, public-port refusal,
Tailscale access, health/SSE, backup, kill/rearm audit, sub-second kill timing, restart within
60 seconds, zero duplicate intents/orders, zero real broker calls, SQLite integrity, and
disposable replay.

## D3-D8 non-compressible sequence

| Gate | Earliest legitimate completion evidence |
|---|---|
| D3 | Five consecutive expected NSE sessions after D1/D2 pass; any fix restarts the sequence. |
| D4 | Exact commissioned image/config passes same-Oracle-host paper/read-only production-readiness validation, including broker/network controls. |
| D5 | Final checklist passes with restore, alerts, kill controls, checksums, and rehearsals. |
| D6 | Separate post-D5 activation record for no more than 10%; no forced test order. |
| D7 | Four sequential stages, each at least two calendar weeks and ten reviewed sessions. |
| D8 | The 100% stage completes cleanly and the full operations package is handed over. |

Synthetic evidence, local tests, early approvals, or waiting less than the specified elapsed
period never substitute for these gates.

## Current operator action

Create the superseding immutable release for the already verified D2 candidate, update D0
private evidence, and rerun the D2 evaluator. Do not enable either live-order flag.
