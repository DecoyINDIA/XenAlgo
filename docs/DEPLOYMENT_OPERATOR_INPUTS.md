# Deployment Operator Inputs and Remaining Gates

**Recorded:** 2026-07-12

**Purpose:** Durable, non-secret handoff for completing D1-D9 after the Oracle paper release.
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
- D1 and D2 remain fail-closed because heartbeat, real-phone alerts, Fyers authentication,
  and the scheduled live-data paper runtime are not yet proven.

The exact host address, image digest, checksums, approval identifier, and gate JSON remain in
the gitignored `Diary/deployment/` evidence directory.

## Host-local secrets to provision

Edit `/etc/xenalgo/xenalgo.env` directly on the host over Tailscale SSH. Do not paste values
into chat, tickets, documentation, shell history, git, image build arguments, or logs.

Required Fyers values:

| Variable | Purpose | Current evidence |
|---|---|---|
| `FYERS_APP_ID` | Approved Fyers API application identity | Missing |
| `FYERS_SECRET_KEY` | Application secret | Missing |
| `FYERS_REDIRECT_URI` | Exact registered OAuth redirect URI | Missing |
| `FYERS_PIN` | Operator-owned daily authentication input | Missing |
| `FYERS_TOTP_SECRET` | Operator-owned TOTP seed | Missing |
| `XENALGO_STATIC_IP_PRIMARY` | Broker/network identity if required by the approved contract | Missing |
| `XENALGO_STATIC_IP_SECONDARY` | Secondary network identity if required | Missing |

Required operations values:

| Variable | Purpose | Current evidence |
|---|---|---|
| `XENALGO_HEARTBEAT_URL` | Operator-owned external heartbeat endpoint | Missing |
| `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | Real-phone alert channel | Missing |
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

## Evidence required to close D1

- External heartbeat receives repeated one-minute health pings.
- A critical test reaches the operator's real phone.
- The independent/fallback alert behavior required by the approved operations policy is
  recorded.
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

Already proven on the deployed image: immutable identity, paper config, public-port refusal,
Tailscale access, health/SSE, backup, kill/rearm audit, sub-second kill timing, restart within
60 seconds, zero duplicate intents/orders, zero real broker calls, SQLite integrity, and
disposable replay.

## D3-D9 non-compressible sequence

| Gate | Earliest legitimate completion evidence |
|---|---|
| D3 | Five consecutive expected NSE sessions after D1/D2 pass; any fix restarts the sequence. |
| D4 | Operator-selected paid India host/account/capital and verified broker/network controls. |
| D5 | Exact commissioned image/config passes paid-host paper/read-only parity. |
| D6 | Final checklist passes with restore, alerts, kill controls, checksums, and rehearsals. |
| D7 | Separate post-D6 activation record for no more than 10%; no forced test order. |
| D8 | Four sequential stages, each at least two calendar weeks and ten reviewed sessions. |
| D9 | The 100% stage completes cleanly and the full operations package is handed over. |

Synthetic evidence, local tests, early approvals, or waiting less than the specified elapsed
period never substitute for these gates.

## Current operator action

Provision the missing host-local Fyers, heartbeat, and phone-alert values using the procedure
above, then run and retain redacted auth/alert evidence. Do not enable either live-order flag.
