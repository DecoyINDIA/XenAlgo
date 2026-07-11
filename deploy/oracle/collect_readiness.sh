#!/usr/bin/env bash
set -euo pipefail

# Produces non-secret facts only. Boolean acceptance fields still require operator review.
HOST="$(hostname)"
TAILNET_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
cat <<EOF
{
  "host_id": "${HOST}",
  "provider": "oracle",
  "region": "OPERATOR_REQUIRED",
  "os_version": "$(. /etc/os-release && printf '%s' "${PRETTY_NAME}")",
  "tailnet_ip": "${TAILNET_IP}",
  "tailscale_healthy": $(tailscale status >/dev/null 2>&1 && echo true || echo false),
  "docker_version": "$(docker --version 2>/dev/null | sed 's/"/\\"/g' || true)",
  "systemd_version": "$(systemctl --version | head -n1 | sed 's/"/\\"/g')",
  "live_trading_enabled": false,
  "broker_order_api_enabled": false
}
EOF
