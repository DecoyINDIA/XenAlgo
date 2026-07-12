#!/usr/bin/env bash
set -euo pipefail

for service in docker tailscaled firewalld xenalgo-paper; do
  systemctl is-active --quiet "${service}.service"
done

[[ "$(timedatectl show -p NTPSynchronized --value)" == "yes" ]]

root_use="$(df --output=pcent / | tail -n1 | tr -dc '0-9')"
available_mb="$(awk '/MemAvailable:/ {printf "%d", $2 / 1024}' /proc/meminfo)"
[[ "${root_use}" -lt 85 ]]
[[ "${available_mb}" -ge 100 ]]

bind_host="$(tr -d '\r' < /etc/xenalgo/xenalgo.env | awk -F= '$1 == "TAILSCALE_BIND_HOST" {print $2; exit}')"
[[ -n "${bind_host}" ]]
curl -fsS --max-time 5 "http://${bind_host}:8080/health" >/dev/null

if [[ -n "${XENALGO_HEARTBEAT_URL:-}" ]]; then
  curl -fsS --max-time 10 "${XENALGO_HEARTBEAT_URL}" >/dev/null
fi
