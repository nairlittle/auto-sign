#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/auto-sign/app}"
DATA_DIR="${DATA_DIR:-/opt/auto-sign/data}"
IMAGE_NAME="${IMAGE_NAME:-auto-sign:latest}"
CRON_SCHEDULE="${CRON_SCHEDULE:-30 8 * * *}"

if [[ $# -ge 1 ]]; then
  APP_DIR="$1"
fi

if [[ $# -ge 2 ]]; then
  DATA_DIR="$2"
fi

if [[ $# -ge 3 ]]; then
  IMAGE_NAME="$3"
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab is required but was not found in PATH." >&2
  exit 1
fi

APP_DIR="$(cd "${APP_DIR}" && pwd)"
DATA_DIR="$(mkdir -p "${DATA_DIR}" && cd "${DATA_DIR}" && pwd)"
ENV_FILE="${DATA_DIR}/.env"
CRON_LOG_FILE="${CRON_LOG_FILE:-${DATA_DIR}/cron.log}"
DOCKER_BIN="$(command -v docker)"
RUN_CMD="cd \"${APP_DIR}\" && \"${DOCKER_BIN}\" run --rm --env-file \"${ENV_FILE}\" -v \"${DATA_DIR}:/data\" \"${IMAGE_NAME}\" >> \"${CRON_LOG_FILE}\" 2>&1"
CRON_LINE="${CRON_SCHEDULE} ${RUN_CMD}"

echo "[1/4] Checking required paths"
if [[ ! -d "${APP_DIR}" ]]; then
  echo "Application directory does not exist: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file does not exist: ${ENV_FILE}" >&2
  exit 1
fi

echo "[2/4] Updating repository"
git -C "${APP_DIR}" pull --ff-only

echo "[3/4] Building image"
"${DOCKER_BIN}" build -t "${IMAGE_NAME}" "${APP_DIR}"

echo "[4/4] Installing crontab entry"
TMP_CRON="$(mktemp)"
trap 'rm -f "${TMP_CRON}"' EXIT

if crontab -l >/dev/null 2>&1; then
  crontab -l | grep -Fv "${RUN_CMD}" > "${TMP_CRON}" || true
fi
echo "${CRON_LINE}" >> "${TMP_CRON}"
crontab "${TMP_CRON}"

echo "Crontab installation complete."
echo "APP_DIR=${APP_DIR}"
echo "DATA_DIR=${DATA_DIR}"
echo "IMAGE_NAME=${IMAGE_NAME}"
echo "CRON_SCHEDULE=${CRON_SCHEDULE}"
echo "CRON_LOG_FILE=${CRON_LOG_FILE}"
