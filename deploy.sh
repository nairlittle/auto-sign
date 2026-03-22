#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/auto-sign/app}"
DATA_DIR="${DATA_DIR:-/opt/auto-sign/data}"
IMAGE_NAME="${IMAGE_NAME:-auto-sign:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-auto-sign}"
ENV_FILE="${DATA_DIR}/.env"

if [[ $# -ge 1 ]]; then
  APP_DIR="$1"
fi

if [[ $# -ge 2 ]]; then
  DATA_DIR="$2"
  ENV_FILE="${DATA_DIR}/.env"
fi

if [[ $# -ge 3 ]]; then
  CONTAINER_NAME="$3"
fi

if [[ $# -ge 4 ]]; then
  IMAGE_NAME="$4"
fi

echo "[1/5] Checking required paths"
if [[ ! -d "${APP_DIR}" ]]; then
  echo "App directory does not exist: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file does not exist: ${ENV_FILE}" >&2
  exit 1
fi

mkdir -p "${DATA_DIR}"

echo "[2/5] Updating repository"
git -C "${APP_DIR}" pull --ff-only

echo "[3/5] Building image"
docker build -t "${IMAGE_NAME}" "${APP_DIR}"

echo "[4/5] Replacing container"
if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  docker rm -f "${CONTAINER_NAME}"
fi

echo "[5/5] Starting container"
docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -v "${DATA_DIR}:/data" \
  "${IMAGE_NAME}"

echo "Deployment completed"
echo "APP_DIR=${APP_DIR}"
echo "DATA_DIR=${DATA_DIR}"
echo "CONTAINER_NAME=${CONTAINER_NAME}"
echo "IMAGE_NAME=${IMAGE_NAME}"
