#!/usr/bin/env bash
#
# backup_to_filemanager.sh — backup CancionesPersonalizadas (jobs.db + output/)
# to ECFileManager (https://ecfilemanager.duckdns.org).
#
# Sube un tar.gz timestamped a la aplicación "CancionesPersonalizadas-Backups".
# Pensado para correr desde cron (ver README / crontab).
#
# Uso:  scripts/backup_to_filemanager.sh
#
set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────────
REPO_DIR="/home/servidor/Descargas/CancionesPersonalizadas"
FM_BASE="https://ecfilemanager.duckdns.org/api"
APP_ID="65b82593-7fe5-4653-9160-5e6a033fd0f8"   # CancionesPersonalizadas-Backups
LOG_TAG="[canciones-backup]"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_NAME="canciones_backup_${TIMESTAMP}.tar.gz"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log() { echo "${LOG_TAG} $(date +%F_%T) $*"; }

# ── 0. Autenticación (JWT de servicio) ─────────────────────────────────────────
# El FileManager valida JWT HS256 con el secreto compartido. Se mintea un token
# de servicio de corta vida (1h) para autorizar la subida.
JWT_SHARED_SECRET="$(grep -E '^JWT_SHARED_SECRET=' "${REPO_DIR}/.env" | tail -1 | cut -d= -f2-)"
if [ -z "${JWT_SHARED_SECRET}" ]; then
    log "ERROR: JWT_SHARED_SECRET no encontrado en ${REPO_DIR}/.env" >&2
    exit 1
fi
export JWT_SHARED_SECRET

TOKEN="$(python3 "${REPO_DIR}/scripts/mint_backup_jwt.py")"
if [ -z "${TOKEN}" ]; then
    log "ERROR: no se pudo mintear el JWT de servicio" >&2
    exit 1
fi
log "JWT de servicio minteado (1h de validez)."

# ── 1. Empaquetar ──────────────────────────────────────────────────────────────
log "Empaquetando jobs.db + output/ en ${BACKUP_NAME} ..."
tar -czf "${TMP_DIR}/${BACKUP_NAME}" \
    -C "${REPO_DIR}" \
    jobs.db \
    output

SIZE="$(du -h "${TMP_DIR}/${BACKUP_NAME}" | cut -f1)"
log "Backup generado: ${BACKUP_NAME} (${SIZE})"

# ── 2. Subir a FileManager ─────────────────────────────────────────────────────
log "Subiendo a FileManager (app ${APP_ID}) ..."
RESPONSE="$(curl -sS -f -m 300 \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "file=@${TMP_DIR}/${BACKUP_NAME};type=application/gzip" \
    -F "isTemporary=false" \
    -F "description=CancionesPersonalizadas backup ${TIMESTAMP}" \
    "${FM_BASE}/file/application/${APP_ID}")"

log "Subido correctamente. Respuesta: ${RESPONSE}"
log "OK — backup ${BACKUP_NAME} en FileManager."
