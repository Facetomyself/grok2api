#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CONFIG_FILE="${CONFIG_FILE:-$ROOT_DIR/data/config.toml}"
API_KEY="${API_KEY:-${AUTO_REGISTER_API_KEY:-}}"
COUNT="${COUNT:-10}"
CONCURRENCY="${CONCURRENCY:-1}"
POOL="${POOL:-ssoBasic}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1800}"
FORCE_STOP_RUNNING="${FORCE_STOP_RUNNING:-0}"
DRY_RUN=0
CURL_FAIL_OPT="--fail"

usage() {
  cat <<'EOF'
用法:
  cron_auto_register.sh [options]

Options:
  --base-url URL             API 地址（默认: http://127.0.0.1:8000）
  --api-key KEY              Bearer Key（默认从环境变量或 data/config.toml 读取）
  --config-file FILE         配置文件路径（默认: ./data/config.toml）
  --count N                  注册数量（默认: 10）
  --concurrency N            注册并发（默认: 1）
  --pool NAME                Token 池（默认: ssoBasic）
  --poll-interval SEC        状态轮询间隔秒（默认: 5）
  --timeout SEC              最长等待秒（默认: 1800）
  --force-stop-running       若已有任务在跑，先停止再启动本次任务
  --dry-run                  只打印参数，不发起请求
  -h, --help                 显示帮助

示例:
  /root/grok2api/scripts/cron_auto_register.sh --count 50 --concurrency 1
  API_KEY=sk-xxx /root/grok2api/scripts/cron_auto_register.sh --count 20
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "缺少命令: $cmd" >&2
    exit 127
  }
}

load_api_key_from_config() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  awk '
    BEGIN { in_app=0 }
    /^\[app\][[:space:]]*$/ { in_app=1; next }
    /^\[/ && in_app==1 { exit }
    in_app==1 && /^[[:space:]]*api_key[[:space:]]*=/ {
      line=$0
      sub(/^[^=]*=[[:space:]]*/, "", line)
      sub(/[[:space:]]*#.*/, "", line)
      gsub(/^[[:space:]]*"/, "", line)
      gsub(/"[[:space:]]*$/, "", line)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      print line
      exit
    }
  ' "$file"
}

http_get() {
  local path="$1"
  curl -sS "$CURL_FAIL_OPT" \
    -H "Authorization: Bearer ${API_KEY}" \
    "${BASE_URL}${path}"
}

http_post() {
  local path="$1"
  local body="$2"
  curl -sS "$CURL_FAIL_OPT" \
    -X POST \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "${BASE_URL}${path}"
}

parse_status_fields() {
  python3 -c '
import json
import sys
obj = json.load(sys.stdin)
print(str(obj.get("status", "")))
print(str(obj.get("job_id", "")))
print(str(obj.get("completed", 0)))
print(str(obj.get("added", 0)))
print(str(obj.get("errors", 0)))
print(str(obj.get("last_error", "") or ""))
'
}

parse_start_fields() {
  python3 -c '
import json
import sys
obj = json.load(sys.stdin)
job = obj.get("job") or {}
print(str(obj.get("status", "")))
print(str(job.get("job_id", "")))
print(str(job.get("concurrency", "")))
print(str(job.get("total", "")))
'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"; shift 2 ;;
    --api-key)
      API_KEY="$2"; shift 2 ;;
    --config-file)
      CONFIG_FILE="$2"; shift 2 ;;
    --count)
      COUNT="$2"; shift 2 ;;
    --concurrency)
      CONCURRENCY="$2"; shift 2 ;;
    --pool)
      POOL="$2"; shift 2 ;;
    --poll-interval)
      POLL_INTERVAL="$2"; shift 2 ;;
    --timeout)
      TIMEOUT_SECONDS="$2"; shift 2 ;;
    --force-stop-running)
      FORCE_STOP_RUNNING=1; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 2 ;;
  esac
done

require_cmd curl
require_cmd python3

if curl --help all 2>/dev/null | grep -q -- '--fail-with-body'; then
  CURL_FAIL_OPT="--fail-with-body"
fi

if [[ -z "${API_KEY}" ]]; then
  API_KEY="$(load_api_key_from_config "$CONFIG_FILE" || true)"
fi

if [[ -z "${API_KEY}" ]]; then
  echo "未找到 API_KEY。请传 --api-key，或在配置文件 [app].api_key 设置。" >&2
  exit 2
fi

if [[ "$DRY_RUN" == "1" ]]; then
  log "DRY RUN"
  log "BASE_URL=${BASE_URL}"
  log "CONFIG_FILE=${CONFIG_FILE}"
  log "COUNT=${COUNT}, CONCURRENCY=${CONCURRENCY}, POOL=${POOL}"
  log "POLL_INTERVAL=${POLL_INTERVAL}, TIMEOUT_SECONDS=${TIMEOUT_SECONDS}"
  exit 0
fi

log "检查当前注册任务状态..."
CURRENT_STATUS_JSON="$(http_get '/api/v1/admin/tokens/auto-register/status')"
mapfile -t CURRENT_FIELDS < <(printf '%s' "$CURRENT_STATUS_JSON" | parse_status_fields)
CURRENT_STATUS="${CURRENT_FIELDS[0]:-}"
CURRENT_JOB_ID="${CURRENT_FIELDS[1]:-}"

if [[ "$CURRENT_STATUS" == "running" || "$CURRENT_STATUS" == "starting" ]]; then
  if [[ "$FORCE_STOP_RUNNING" == "1" ]]; then
    log "发现已有任务 job_id=${CURRENT_JOB_ID}，先停止..."
    http_post "/api/v1/admin/tokens/auto-register/stop?job_id=${CURRENT_JOB_ID}" '{}' >/dev/null
    sleep 2
  else
    log "已有任务在运行（job_id=${CURRENT_JOB_ID}），本次跳过。"
    exit 0
  fi
fi

REQUEST_BODY="$(printf '{"count":%s,"concurrency":%s,"pool":"%s"}' "$COUNT" "$CONCURRENCY" "$POOL")"
log "启动自动注册: ${REQUEST_BODY}"
START_JSON="$(http_post '/api/v1/admin/tokens/auto-register' "$REQUEST_BODY")"
mapfile -t START_FIELDS < <(printf '%s' "$START_JSON" | parse_start_fields)
START_STATUS="${START_FIELDS[0]:-}"
JOB_ID="${START_FIELDS[1]:-}"
ACTUAL_CONCURRENCY="${START_FIELDS[2]:-}"
ACTUAL_TOTAL="${START_FIELDS[3]:-}"

if [[ -z "$JOB_ID" ]]; then
  echo "启动任务失败，返回: $START_JSON" >&2
  exit 1
fi

log "任务已启动 job_id=${JOB_ID}, status=${START_STATUS}, total=${ACTUAL_TOTAL}, concurrency=${ACTUAL_CONCURRENCY}"
START_EPOCH="$(date +%s)"

while true; do
  STATUS_JSON="$(http_get "/api/v1/admin/tokens/auto-register/status?job_id=${JOB_ID}")"
  mapfile -t FIELDS < <(printf '%s' "$STATUS_JSON" | parse_status_fields)

  STATUS="${FIELDS[0]:-}"
  COMPLETED="${FIELDS[2]:-0}"
  ADDED="${FIELDS[3]:-0}"
  ERRORS="${FIELDS[4]:-0}"
  LAST_ERROR="${FIELDS[5]:-}"

  log "job=${JOB_ID} status=${STATUS} progress=${COMPLETED}/${ACTUAL_TOTAL} added=${ADDED} errors=${ERRORS} last_error=${LAST_ERROR}"

  case "$STATUS" in
    completed)
      if [[ "${ERRORS}" == "0" ]]; then
        log "任务完成且无错误。"
        exit 0
      fi
      log "任务完成，但存在错误数=${ERRORS}。"
      exit 3
      ;;
    failed|stopped)
      log "任务异常结束，status=${STATUS}。"
      exit 4
      ;;
  esac

  if [[ "$TIMEOUT_SECONDS" -gt 0 ]]; then
    NOW="$(date +%s)"
    ELAPSED="$((NOW - START_EPOCH))"
    if [[ "$ELAPSED" -ge "$TIMEOUT_SECONDS" ]]; then
      log "等待超时（${TIMEOUT_SECONDS}s），退出。"
      exit 124
    fi
  fi

  sleep "$POLL_INTERVAL"
done
