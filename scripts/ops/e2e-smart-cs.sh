#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_NAME="dev"
SERVICES_CSV="ljwx-website,ljwx-dify,ljwx-chat"
TARGETS_FILE="scripts/smoke/targets.local-k3s.json"
WORKFLOW_TIMEOUT_SEC=3600
QUEUE_TIMEOUT_SEC=1800
PROMOTE_TIMEOUT_SEC=1800
POLL_INTERVAL_SEC=20
SKIP_TRIGGER="false"
SKIP_SMOKE="false"
SMOKE_DRY_RUN="false"
ALLOW_SMOKE_FAILURES="false"
ALLOW_PROMOTE_PENDING="false"

log() {
  echo "[smart-cs-e2e] $*"
}

err() {
  echo "[smart-cs-e2e][错误] $*" >&2
}

usage() {
  cat <<'USAGE'
用途:
  一键执行 Smart CS 端到端验证：
  Gate -> 三仓 build-and-enqueue -> queue/promote -> ArgoCD -> smoke -> evidence

用法:
  bash scripts/ops/e2e-smart-cs.sh [options]

选项:
  --env <dev|demo|prod>         目标环境（默认: dev）
  --services <csv>              服务列表（默认: ljwx-website,ljwx-dify,ljwx-chat）
  --targets <path>              smoke targets 文件（默认: scripts/smoke/targets.local-k3s.json）
  --workflow-timeout-sec <n>    每个 workflow 等待秒数（默认: 3600）
  --queue-timeout-sec <n>       等待 queue 入列秒数（默认: 1800）
  --promote-timeout-sec <n>     等待 promoted 秒数（默认: 1800）
  --poll-interval-sec <n>       轮询间隔秒数（默认: 20）
  --skip-trigger                跳过触发三仓 workflow（只做后半段验证）
  --skip-smoke                  跳过 smoke 执行
  --smoke-dry-run               smoke 使用 --dry-run
  --allow-smoke-failures        smoke 使用 --allow-failures
  --allow-promote-pending       promoted 超时不失败（仅告警）
  -h, --help                    显示帮助
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_NAME="${2:-}"
      shift 2
      ;;
    --services)
      SERVICES_CSV="${2:-}"
      shift 2
      ;;
    --targets)
      TARGETS_FILE="${2:-}"
      shift 2
      ;;
    --workflow-timeout-sec)
      WORKFLOW_TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    --queue-timeout-sec)
      QUEUE_TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    --promote-timeout-sec)
      PROMOTE_TIMEOUT_SEC="${2:-}"
      shift 2
      ;;
    --poll-interval-sec)
      POLL_INTERVAL_SEC="${2:-}"
      shift 2
      ;;
    --skip-trigger)
      SKIP_TRIGGER="true"
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE="true"
      shift
      ;;
    --smoke-dry-run)
      SMOKE_DRY_RUN="true"
      shift
      ;;
    --allow-smoke-failures)
      ALLOW_SMOKE_FAILURES="true"
      shift
      ;;
    --allow-promote-pending)
      ALLOW_PROMOTE_PENDING="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "未知参数: $1"
      usage
      exit 2
      ;;
  esac
done

required_cmds=(jq kubectl python3 uvx)
if [[ "$SKIP_TRIGGER" != "true" ]]; then
  required_cmds+=(gh)
fi

for cmd in "${required_cmds[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "缺少命令: $cmd"
    exit 2
  fi
done

if [[ "$SKIP_TRIGGER" != "true" ]]; then
  if ! gh auth status >/dev/null 2>&1; then
    err "gh 未登录，请先执行: gh auth login"
    exit 2
  fi
fi

if [[ ! -f "release/queue.yaml" ]]; then
  err "当前目录不是 ljwx-deploy 仓库根目录"
  exit 2
fi

if [[ ! -f "$TARGETS_FILE" ]]; then
  err "smoke targets 文件不存在: $TARGETS_FILE"
  exit 2
fi

declare -A REPO_BY_SERVICE=(
  ["ljwx-website"]="BrunoGao/ljwx-website"
  ["ljwx-dify"]="BrunoGao/ljwx-dify"
  ["ljwx-chat"]="BrunoGao/ljwx-chat"
)

IFS=',' read -r -a SERVICES <<< "$SERVICES_CSV"
if [[ "${#SERVICES[@]}" -eq 0 ]]; then
  err "--services 不能为空"
  exit 2
fi

for service in "${SERVICES[@]}"; do
  if [[ -z "${REPO_BY_SERVICE[$service]:-}" ]]; then
    err "未配置仓库映射的服务: $service"
    exit 2
  fi
done

resolve_run_id() {
  local repo="$1"
  local since_ts="$2"
  local run_id=""
  local deadline=$((SECONDS + 180))

  while (( SECONDS < deadline )); do
    run_id="$(gh run list -R "$repo" -w build-and-enqueue --event workflow_dispatch --json databaseId,createdAt -L 30 \
      | jq -r --arg since "$since_ts" '[.[] | select(.createdAt >= $since)] | sort_by(.createdAt) | reverse | .[0].databaseId // empty')"
    if [[ -n "$run_id" ]]; then
      echo "$run_id"
      return 0
    fi
    sleep 3
  done

  return 1
}

wait_run_success() {
  local repo="$1"
  local run_id="$2"
  local deadline=$((SECONDS + WORKFLOW_TIMEOUT_SEC))

  while (( SECONDS < deadline )); do
    local info
    info="$(gh run view "$run_id" -R "$repo" --json status,conclusion,url 2>/dev/null || true)"
    local status conclusion url
    status="$(jq -r '.status // empty' <<<"$info")"
    conclusion="$(jq -r '.conclusion // empty' <<<"$info")"
    url="$(jq -r '.url // empty' <<<"$info")"

    if [[ "$status" == "completed" ]]; then
      if [[ "$conclusion" == "success" ]]; then
        log "workflow 成功: $repo run_id=$run_id"
        return 0
      fi
      err "workflow 失败: $repo run_id=$run_id conclusion=$conclusion url=$url"
      return 1
    fi

    log "等待 workflow 完成: $repo run_id=$run_id status=${status:-unknown}"
    sleep "$POLL_INTERVAL_SEC"
  done

  err "workflow 等待超时: $repo run_id=$run_id"
  return 1
}

wait_queue_new_entries() {
  local since_ts="$1"
  local deadline=$((SECONDS + QUEUE_TIMEOUT_SEC))

  while (( SECONDS < deadline )); do
    if uvx --with pyyaml python - "$since_ts" "$ENV_NAME" "$SERVICES_CSV" <<'PY'
import sys
from datetime import datetime, timezone
import yaml

since = datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00")).astimezone(timezone.utc)
env = sys.argv[2]
services = [x for x in sys.argv[3].split(",") if x]

with open("release/queue.yaml", "r", encoding="utf-8") as f:
    q = yaml.safe_load(f) or {}

states = ["pending", "promoted", "failed", "superseded"]
missing = []
for svc in services:
    latest = None
    for st in states:
        for item in q.get(st, []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("service") != svc or item.get("env") != env:
                continue
            created_at = item.get("createdAt") or ""
            try:
                ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
            if ts < since:
                continue
            if latest is None or ts > latest[0]:
                latest = (ts, st, item.get("id", ""))
    if latest is None:
        missing.append(svc)
    else:
        print(f"QUEUE_OK {svc} state={latest[1]} id={latest[2]}")

if missing:
    print("QUEUE_MISSING " + ",".join(missing), file=sys.stderr)
    raise SystemExit(1)
PY
    then
      return 0
    fi

    log "等待 queue 入列..."
    sleep "$POLL_INTERVAL_SEC"
  done

  err "queue 入列等待超时"
  return 1
}

wait_promoted_entries() {
  local since_ts="$1"
  local deadline=$((SECONDS + PROMOTE_TIMEOUT_SEC))

  while (( SECONDS < deadline )); do
    if uvx --with pyyaml python - "$since_ts" "$ENV_NAME" "$SERVICES_CSV" <<'PY'
import sys
from datetime import datetime, timezone
import yaml

since = datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00")).astimezone(timezone.utc)
env = sys.argv[2]
services = [x for x in sys.argv[3].split(",") if x]

with open("release/queue.yaml", "r", encoding="utf-8") as f:
    q = yaml.safe_load(f) or {}

missing = []
for svc in services:
    latest = None
    for item in q.get("promoted", []) or []:
      if not isinstance(item, dict):
          continue
      if item.get("service") != svc or item.get("env") != env:
          continue
      created_at = item.get("createdAt") or ""
      try:
          ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).astimezone(timezone.utc)
      except ValueError:
          continue
      if ts < since:
          continue
      if latest is None or ts > latest[0]:
          latest = (ts, item.get("id", ""), item.get("promotedAt", ""))

    if latest is None:
        missing.append(svc)
    else:
        print(f"PROMOTED_OK {svc} id={latest[1]} promotedAt={latest[2]}")

if missing:
    print("PROMOTED_MISSING " + ",".join(missing), file=sys.stderr)
    raise SystemExit(1)
PY
    then
      return 0
    fi

    log "等待 promoter 出列..."
    sleep "$POLL_INTERVAL_SEC"
  done

  return 1
}

check_argocd_apps() {
  log "检查 ArgoCD 应用健康状态"

  local app_json
  app_json="$(uvx --with pyyaml python - "$ENV_NAME" "$SERVICES_CSV" <<'PY'
import json
import sys
import yaml

env = sys.argv[1]
services = [x for x in sys.argv[2].split(',') if x]

with open("release/services.yaml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

apps = []
for svc in services:
    app = (
        data.get("services", {})
        .get(svc, {})
        .get("envs", {})
        .get(env, {})
        .get("argocdApp")
    )
    if not app:
        raise SystemExit(f"missing argocdApp mapping for service={svc} env={env}")
    apps.append(app)

print(json.dumps(apps))
PY
)"

  mapfile -t app_names < <(jq -r '.[]' <<<"$app_json")
  for app in "${app_names[@]}"; do
    local sync health
    sync="$(kubectl -n argocd get applications.argoproj.io "$app" -o jsonpath='{.status.sync.status}')"
    health="$(kubectl -n argocd get applications.argoproj.io "$app" -o jsonpath='{.status.health.status}')"
    log "argocd app=$app sync=$sync health=$health"
    if [[ "$sync" != "Synced" || "$health" != "Healthy" ]]; then
      err "ArgoCD 状态异常: app=$app sync=$sync health=$health"
      return 1
    fi
  done

  return 0
}

run_smoke_subset() {
  local tmp_targets
  tmp_targets="$(mktemp /tmp/smart-cs-smoke-targets.XXXXXX.json)"

  local services_json
  services_json="$(printf '%s\n' "${SERVICES[@]}" | jq -R . | jq -s .)"

  jq --argjson services "$services_json" '{profile: .profile, targets: [ .targets[] | select(.service as $s | $services | index($s)) ]}' "$TARGETS_FILE" > "$tmp_targets"

  local target_count
  target_count="$(jq '.targets | length' "$tmp_targets")"
  if [[ "$target_count" -lt 1 ]]; then
    err "过滤后的 smoke targets 为空: $tmp_targets"
    rm -f "$tmp_targets"
    return 1
  fi

  for service in "${SERVICES[@]}"; do
    if ! jq -e --arg svc "$service" '.targets | any(.service == $svc)' "$tmp_targets" >/dev/null; then
      err "smoke targets 缺少服务: $service"
      rm -f "$tmp_targets"
      return 1
    fi
  done

  local args=(python3 scripts/smoke/run_smoke.py --targets "$tmp_targets" --queue release/queue.yaml)
  if [[ "$SMOKE_DRY_RUN" == "true" ]]; then
    args+=(--dry-run)
  fi
  if [[ "$ALLOW_SMOKE_FAILURES" == "true" ]]; then
    args+=(--allow-failures)
  fi

  log "执行 smoke: ${args[*]}"
  "${args[@]}"

  rm -f "$tmp_targets"
  return 0
}

print_evidence_summary() {
  uvx --with pyyaml python - "$ENV_NAME" "$SERVICES_CSV" <<'PY'
import glob
import os
import sys
from datetime import datetime, timezone
import yaml

env = sys.argv[1]
services = [x for x in sys.argv[2].split(',') if x]

records = []
for path in glob.glob("evidence/records/*.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if data.get("service") in services and data.get("env") == env:
        ts_text = (data.get("tests", {}).get("smoke", {}).get("checkedAt")
                   or data.get("deploy", {}).get("syncedAt")
                   or data.get("promotedAt")
                   or "1970-01-01T00:00:00Z")
        try:
            ts = datetime.fromisoformat(str(ts_text).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            ts = datetime(1970, 1, 1, tzinfo=timezone.utc)
        records.append((data.get("service"), ts, data))

print("EVIDENCE_SUMMARY")
for svc in services:
    cand = [item for item in records if item[0] == svc]
    if not cand:
        print(f"- {svc}: NO_RECORD")
        continue
    _, _, latest = sorted(cand, key=lambda x: x[1], reverse=True)[0]
    smoke = (((latest.get("tests") or {}).get("smoke") or {}).get("status") or "unknown")
    queue_id = (((latest.get("deploy") or {}).get("queueId")) or "")
    checked = (((latest.get("tests") or {}).get("smoke") or {}).get("checkedAt") or "")
    print(f"- {svc}: smoke={smoke} queue_id={queue_id} checked_at={checked}")
PY
}

START_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
QUEUE_REFERENCE_TS="$START_TS"
log "开始执行 E2E，env=$ENV_NAME services=$SERVICES_CSV start=$START_TS"

log "步骤 1/7: 执行 deploy gate 本地校验"
bash scripts/verify.sh

log "步骤 2/7: 校验三仓 n8n 模板已回写"
for service in "${SERVICES[@]}"; do
  local_repo="/root/codes/$service"
  manifest_path="$local_repo/config/n8n/workflows/smart-cs/manifest.yaml"
  if [[ ! -f "$manifest_path" ]]; then
    err "缺少模板清单: $manifest_path"
    exit 1
  fi
  log "模板存在: $manifest_path"
done

if [[ "$SKIP_TRIGGER" != "true" ]]; then
  log "步骤 3/7: 触发三仓 build-and-enqueue"
  for service in "${SERVICES[@]}"; do
    repo="${REPO_BY_SERVICE[$service]}"
    trigger_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    log "触发 workflow: repo=$repo env=$ENV_NAME"
    gh workflow run build-and-enqueue.yml -R "$repo" --ref main -f target_env="$ENV_NAME"

    run_id="$(resolve_run_id "$repo" "$trigger_ts" || true)"
    if [[ -z "$run_id" ]]; then
      err "无法解析 workflow run id: repo=$repo"
      exit 1
    fi
    log "捕获 run_id: repo=$repo run_id=$run_id"

    wait_run_success "$repo" "$run_id"
  done
else
  log "步骤 3/7: 已跳过 workflow 触发（--skip-trigger）"
  QUEUE_REFERENCE_TS="1970-01-01T00:00:00Z"
  log "跳过触发模式下，queue/promoted 校验将使用全量历史记录"
fi

log "步骤 4/7: 等待 queue 入列"
wait_queue_new_entries "$QUEUE_REFERENCE_TS"

log "步骤 5/7: 等待 promoter 出列"
if ! wait_promoted_entries "$QUEUE_REFERENCE_TS"; then
  if [[ "$ALLOW_PROMOTE_PENDING" == "true" ]]; then
    log "告警: promoter 出列超时，但已允许继续（--allow-promote-pending）"
  else
    err "promoter 出列超时"
    exit 1
  fi
fi

log "步骤 6/7: 检查 ArgoCD 健康状态"
check_argocd_apps

if [[ "$SKIP_SMOKE" != "true" ]]; then
  log "步骤 7/7: 执行 smoke"
  run_smoke_subset
else
  log "步骤 7/7: 已跳过 smoke（--skip-smoke）"
fi

log "输出 evidence 摘要"
print_evidence_summary

log "E2E 验证完成"
