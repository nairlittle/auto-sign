#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/auto-sign/app}"
DATA_DIR="${DATA_DIR:-/opt/auto-sign/data}"
IMAGE_NAME="${IMAGE_NAME:-auto-sign:latest}"
CRON_SCHEDULE="${CRON_SCHEDULE:-30 8 * * *}"

usage() {
  cat <<EOF
用法:
  bash deploy.sh
  bash deploy.sh -t "15 9 * * *"

参数:
  -t, --time   自定义 crontab 时间，格式与标准 cron 一致
  -h, --help   显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--time)
      if [[ $# -lt 2 ]]; then
        echo "参数 $1 需要提供时间值。" >&2
        usage
        exit 1
      fi
      CRON_SCHEDULE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "不支持的参数: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "未在 PATH 中找到 git，请先安装或检查环境变量。" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未在 PATH 中找到 docker，请先安装或检查环境变量。" >&2
  exit 1
fi

if ! command -v crontab >/dev/null 2>&1; then
  echo "未在 PATH 中找到 crontab，请先安装或检查环境变量。" >&2
  exit 1
fi

APP_DIR="$(cd "${APP_DIR}" && pwd)"
DATA_DIR="$(mkdir -p "${DATA_DIR}" && cd "${DATA_DIR}" && pwd)"
ENV_FILE="${DATA_DIR}/.env"
ENV_TEMPLATE="${APP_DIR}/.env.example"
CRON_LOG_FILE="${CRON_LOG_FILE:-${DATA_DIR}/cron.log}"
DOCKER_BIN="$(command -v docker)"
RUN_CMD="cd \"${APP_DIR}\" && \"${DOCKER_BIN}\" run --rm --env-file \"${ENV_FILE}\" -v \"${DATA_DIR}:/data\" \"${IMAGE_NAME}\" >> \"${CRON_LOG_FILE}\" 2>&1"
CRON_LINE="${CRON_SCHEDULE} ${RUN_CMD}"

echo "[1/5] 检查必要路径"
if [[ ! -d "${APP_DIR}" ]]; then
  echo "应用目录不存在: ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "环境变量文件不存在: ${ENV_FILE}" >&2
  exit 1
fi

echo "[2/5] 更新仓库"
git -C "${APP_DIR}" pull --ff-only

echo "[3/5] 检查环境变量"
if [[ -f "${ENV_TEMPLATE}" ]]; then
  missing_keys=()
  while IFS= read -r key; do
    [[ -z "${key}" ]] && continue
    if ! grep -Eq "^${key}=" "${ENV_FILE}"; then
      missing_keys+=("${key}")
    fi
  done < <(grep -E '^[A-Z0-9_]+=' "${ENV_TEMPLATE}" | cut -d '=' -f 1)

  if [[ ${#missing_keys[@]} -gt 0 ]]; then
    echo "警告: ${ENV_FILE} 缺少 .env.example 中的以下配置项:" >&2
    printf '  - %s\n' "${missing_keys[@]}" >&2
    echo "请在下一次定时任务执行前检查并补全 ${ENV_FILE}。" >&2
  fi
fi

echo "[4/5] 构建镜像"
"${DOCKER_BIN}" build -t "${IMAGE_NAME}" "${APP_DIR}"

echo "[5/5] 安装 crontab 任务"
TMP_CRON="$(mktemp)"
trap 'rm -f "${TMP_CRON}"' EXIT

if crontab -l >/dev/null 2>&1; then
  crontab -l | grep -Fv "${RUN_CMD}" > "${TMP_CRON}" || true
fi
echo "${CRON_LINE}" >> "${TMP_CRON}"
crontab "${TMP_CRON}"

echo "定时任务安装完成。"
echo "APP_DIR=${APP_DIR}"
echo "DATA_DIR=${DATA_DIR}"
echo "IMAGE_NAME=${IMAGE_NAME}"
echo "CRON_SCHEDULE=${CRON_SCHEDULE}"
echo "CRON_LOG_FILE=${CRON_LOG_FILE}"
