#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/var/lib/xenalgo}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/xenalgo}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/${STAMP}"

install -d -m 700 "${TARGET}"

# The token store and /etc/xenalgo are intentionally outside DATA_DIR and never copied.
if [[ -f "${DATA_DIR}/Diary/state/order_journal.sqlite" ]]; then
  sqlite3 "${DATA_DIR}/Diary/state/order_journal.sqlite" ".backup '${TARGET}/order_journal.sqlite'"
fi
if [[ -d "${DATA_DIR}/Supply" ]]; then
  tar --create --gzip --file "${TARGET}/supply.tar.gz" --directory "${DATA_DIR}" Supply
fi

(cd "${TARGET}" && sha256sum ./* > SHA256SUMS)
