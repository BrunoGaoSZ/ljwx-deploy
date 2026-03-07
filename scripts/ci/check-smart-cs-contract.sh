#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SPRINT_DOC="$ROOT_DIR/docs/smart-cs-implementation-sprints.md"
CONTRACT_DOC="$ROOT_DIR/docs/smart-cs-data-contract.md"

fail() {
  echo "错误: $*" >&2
  exit 1
}

[[ -f "$SPRINT_DOC" ]] || fail "缺少文件: $SPRINT_DOC"
[[ -f "$CONTRACT_DOC" ]] || fail "缺少文件: $CONTRACT_DOC"

cd "$ROOT_DIR"

uvx --with pyyaml --with jsonschema python scripts/platform/validate_router_contracts.py

required_kpis=(KPI-01 KPI-02 KPI-03 KPI-04 KPI-05 KPI-06 KPI-07)
for kpi in "${required_kpis[@]}"; do
  if ! rg -q "$kpi" "$SPRINT_DOC"; then
    fail "Sprint 文档缺少指标: $kpi"
  fi
  if ! rg -q "$kpi" "$CONTRACT_DOC"; then
    fail "数据契约缺少指标映射: $kpi"
  fi
done

required_domains=("知识库数据" "对话数据" "业务数据" "运营数据" "官网内容数据")
for domain in "${required_domains[@]}"; do
  if ! rg -q "$domain" "$CONTRACT_DOC"; then
    fail "数据契约缺少域定义: $domain"
  fi
done

echo "Smart CS contract gate passed."
