#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/xenalgo/app}"
IMAGE_TAG="${IMAGE_TAG:-xenalgo:oracle-paper}"
ENV_DIR="/etc/xenalgo"
DATA_DIR="/var/lib/xenalgo"
BACKUP_DIR="/var/backups/xenalgo"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root with sudo." >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/Dockerfile" ]]; then
  echo "Expected XenAlgo checkout at ${APP_DIR}; Dockerfile was not found." >&2
  exit 1
fi

hour_ist="$(TZ=Asia/Kolkata date +%H%M)"
day_ist="$(TZ=Asia/Kolkata date +%u)"
if (( 10#${day_ist} <= 5 && 10#${hour_ist} >= 900 && 10#${hour_ist} <= 1530 )); then
  echo "Refusing deploy during NSE market hours (09:00-15:30 IST)." >&2
  exit 1
fi

dnf install -y dnf-plugins-core firewalld sqlite

if ! command -v docker >/dev/null 2>&1; then
  dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
fi

systemctl enable --now docker
systemctl enable --now firewalld

if ! command -v tailscale >/dev/null 2>&1; then
  dnf config-manager --add-repo https://pkgs.tailscale.com/stable/oracle/9/tailscale.repo
  dnf install -y tailscale
fi

systemctl enable --now tailscaled

firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --remove-service=http || true
firewall-cmd --permanent --remove-service=https || true
firewall-cmd --reload

mkdir -p "${APP_DIR}" \
  "${ENV_DIR}" \
  "${DATA_DIR}/Diary/state" \
  "${DATA_DIR}/Diary/logs" \
  "${DATA_DIR}/Supply/database" \
  "${BACKUP_DIR}"

chmod 700 "${ENV_DIR}" "${DATA_DIR}" "${BACKUP_DIR}"
chown -R 100:101 "${DATA_DIR}"

if [[ ! -f "${ENV_DIR}/xenalgo.env" ]]; then
  install -m 600 "${APP_DIR}/deploy/oracle/xenalgo.env.example" "${ENV_DIR}/xenalgo.env"
fi

docker build -t "${IMAGE_TAG}" "${APP_DIR}"
docker run --rm "${IMAGE_TAG}" python -m xenalgo --profile live

install -m 644 "${APP_DIR}/deploy/oracle/xenalgo-paper.service" /etc/systemd/system/xenalgo-paper.service
systemctl daemon-reload

echo "Bootstrap complete."
echo "Next: run 'sudo tailscale up', set TAILSCALE_BIND_HOST and XENALGO_CONSOLE_TOKEN in ${ENV_DIR}/xenalgo.env, then start xenalgo-paper.service."
