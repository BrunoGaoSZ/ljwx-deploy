#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET_FILES=(
  "$ROOT_DIR/scripts/smoke/targets.local-k3s.json"
  "$ROOT_DIR/scripts/smoke/targets.orbstack-k3s-cn.json"
)
REQUIRED_SERVICES=(
  "ljwx-website"
  "ljwx-dify"
  "ljwx-dify-web"
  "ljwx-chat"
)

fail() {
  echo "错误: $*" >&2
  exit 1
}

for file in "${TARGET_FILES[@]}"; do
  [[ -f "$file" ]] || fail "缺少 smoke target 文件: $file"

  for service in "${REQUIRED_SERVICES[@]}"; do
    if ! jq -e --arg service "$service" '.targets | any(.service == $service and (.endpoint // "") != "")' "$file" >/dev/null; then
      fail "文件 $file 缺少服务 $service 或 endpoint 为空"
    fi
  done
done

echo "Smart CS smoke target gate passed."
