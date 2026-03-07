#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SPRINT_DOC="$ROOT_DIR/docs/smart-cs-implementation-sprints.md"
CONTRACT_DOC="$ROOT_DIR/docs/smart-cs-data-contract.md"

fail() {
  echo "错误: $*" >&2
  exit 1
}

contains_text() {
  local pattern="$1"
  local file="$2"

  if command -v rg >/dev/null 2>&1; then
    rg -q "$pattern" "$file"
    return
  fi

  grep -q -- "$pattern" "$file"
}

[[ -f "$SPRINT_DOC" ]] || fail "缺少文件: $SPRINT_DOC"
[[ -f "$CONTRACT_DOC" ]] || fail "缺少文件: $CONTRACT_DOC"

cd "$ROOT_DIR"

uvx --with pyyaml --with jsonschema python scripts/platform/validate_router_contracts.py

required_kpis=(KPI-01 KPI-02 KPI-03 KPI-04 KPI-05 KPI-06 KPI-07)
for kpi in "${required_kpis[@]}"; do
  if ! contains_text "$kpi" "$SPRINT_DOC"; then
    fail "Sprint 文档缺少指标: $kpi"
  fi
  if ! contains_text "$kpi" "$CONTRACT_DOC"; then
    fail "数据契约缺少指标映射: $kpi"
  fi
done

required_domains=("知识库数据" "对话数据" "业务数据" "运营数据" "官网内容数据")
for domain in "${required_domains[@]}"; do
  if ! contains_text "$domain" "$CONTRACT_DOC"; then
    fail "数据契约缺少域定义: $domain"
  fi
done

echo "Smart CS contract gate passed."
