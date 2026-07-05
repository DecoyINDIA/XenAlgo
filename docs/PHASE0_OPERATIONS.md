# Phase 0 Operations Runbook

This repo contains the portable app artifact (`Dockerfile`) and config/secrets hygiene needed
for Phase 0. The Oracle Cloud and Tailscale actions below require operator-owned accounts and
must be completed outside the repository.

## Oracle Cloud Always Free

1. Create an ARM A1 instance in Mumbai or Hyderabad.
2. Reserve a public IP and attach it to the instance.
3. Add only the operator SSH key.
4. Keep the cloud security list closed except SSH from the operator's known source IP.
5. Install Docker and Tailscale on the host.
6. Bring Tailscale up with the operator's tailnet approval flow.
7. Confirm no public inbound ports are open except SSH.

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

## App Image

Build the same image for Oracle dev/paper and the future paid live VPS:

```bash
docker build -t xenalgo:phase0 .
docker run --rm --env-file .env xenalgo:phase0 python -m xenalgo --profile live
```

Do not enable `live_trading.enabled` or broker order APIs during Phase 0.
