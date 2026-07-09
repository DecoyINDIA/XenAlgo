# Phase 0 Operations Runbook

This repo contains the portable app artifact (`Dockerfile`) and config/secrets hygiene needed
for Phase 0. The Oracle Cloud and Tailscale actions below require operator-owned accounts and
must be completed outside the repository.

## Oracle Cloud Always Free

### Current OCI paper host

Created 2026-07-06 in OCI India West (Mumbai):

| Field | Value |
|---|---|
| Instance name | `XenAlso` |
| OS image | Oracle Linux 9 |
| Shape | `VM.Standard.E2.1.Micro` |
| VCN | `XenaAlso VCN` |
| Public subnet | `XenAlso Public Subnet` |
| Private IP | `10.0.0.246` |
| Public IP | `80.225.212.3` (ephemeral public IPv4) |
| SSH user | `opc` |

The first creation attempt used `VM.Standard.A1.Flex` with the selected Oracle Linux image
and failed with `Shape VM.Standard.A1.Flex is not valid for image ...`. The working
configuration above uses the compatible Always Free micro shape. If the host is stopped or
recreated, re-check the public IP before using SSH because the current IP is ephemeral.

SSH from Windows PowerShell:

```powershell
ssh -i <path-to-downloaded-private-key> opc@80.225.212.3
```

### Required OCI hardening

1. Confirm the downloaded private key is stored outside the repo, for example under
   `%USERPROFILE%\.ssh\`.
2. Keep the cloud security list closed except SSH from the operator's known source IP.
3. Do not open the FastAPI dashboard publicly; expose it over Tailscale only.
4. Install Docker and Tailscale on the host.
5. Bring Tailscale up with the operator's tailnet approval flow.
6. Confirm no public inbound ports are open except SSH.
7. Record the Tailscale IP/interface in the operator-only host notes before running the
   console.

Suggested host checks:

```powershell
tailscale status
docker --version
```

Suggested remote firewall stance on Ubuntu:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status verbose
```

Suggested remote firewall stance on Oracle Linux 9:

```bash
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --remove-service=http
sudo firewall-cmd --permanent --remove-service=https
sudo firewall-cmd --reload
sudo firewall-cmd --list-all
```

## Local Databases On The Oracle Host

XenAlgo does not need an OCI managed database for paper mode. The databases are local files
on the VM disk:

| Store | Suggested host path | Purpose |
|---|---|---|
| SQLite journal | `/var/lib/xenalgo/Diary/state/order_journal.sqlite` | Paper/live journal, derived state, risk/audit state |
| DuckDB market data | `/var/lib/xenalgo/Supply/database/market_data.duckdb` | Daily OHLCV panel and research/live data reads |

Create the directories after SSH:

```bash
sudo mkdir -p /opt/xenalgo /var/lib/xenalgo/Diary/state /var/lib/xenalgo/Supply/database /var/lib/xenalgo/Diary/logs /var/backups/xenalgo
sudo chown -R "$USER:$USER" /opt/xenalgo /var/lib/xenalgo /var/backups/xenalgo
chmod 700 /var/lib/xenalgo
```

Back up SQLite with `.backup`, not a raw copy while the app may be running:

```bash
sqlite3 /var/lib/xenalgo/Diary/state/order_journal.sqlite ".backup '/var/backups/xenalgo/order_journal-$(date +%F).sqlite'"
```

## App Image

Build the same image for Oracle dev/paper and the future paid live VPS:

```bash
docker build -t xenalgo:phase0 .
docker run --rm --env-file .env xenalgo:phase0 python -m xenalgo --profile live
```

Do not enable `live_trading.enabled` or broker order APIs during Phase 0.

## Oracle Host Deployment Kit

The repository includes an Oracle Linux 9 deployment kit at `deploy/oracle/`:

| File | Purpose |
|---|---|
| `deploy/oracle/bootstrap_oracle_linux9.sh` | Installs Docker, Tailscale, firewalld, local data directories, builds `xenalgo:oracle-paper`, and installs the systemd unit. |
| `deploy/oracle/xenalgo-paper.service` | Runs the Phase 2 console in Docker with host networking so it can bind directly to the Tailscale IP. |
| `deploy/oracle/xenalgo.env.example` | Host-local environment template; copy to `/etc/xenalgo/xenalgo.env` and fill secrets only on the VM. |
| `deploy/oracle/README.md` | End-to-end host checklist and verification commands. |

The bootstrap script refuses to deploy during NSE market hours and keeps the service in the
same paper-mode safety posture enforced by `config/config.live.yaml`: `live_trading.enabled`
and `broker.order_api_enabled` remain `false`.

### 2026-07-09 Deployment Attempt Status

An operator-approved paper-host deployment attempt copied the app bundle to
`/opt/xenalgo/app` and verified the VM copy still had `live_trading.enabled: false` and
`broker.order_api_enabled: false`. The bootstrap then entered `dnf install` on the
`VM.Standard.E2.1.Micro` host and the VM became overloaded: TCP/22 stayed open, but SSH timed
out during banner exchange. Docker, Tailscale, and `xenalgo-paper.service` were not confirmed
installed.

Before retrying:

1. Recover or reboot `XenAlso` from OCI if SSH still reaches TCP/22 but does not complete the
   SSH banner.
2. Recopy the repository bundle so the fixed `deploy/oracle/bootstrap_oracle_linux9.sh`
   time-guard comparison is present on the VM.
3. Rerun the bootstrap and poll `/tmp/xenalgo-bootstrap.log`.
4. Keep the deployment paper-only; do not enable Dhan order APIs or public dashboard ingress.
