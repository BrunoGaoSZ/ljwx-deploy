#!/usr/bin/env bash
set -euo pipefail

REPO_PATH="${PWD}"
SERVICE_NAME=""
STRICT_MODE="false"
SKIP_TEMPLATES_CHECK="false"
DEPLOY_ROOT="${DEPLOY_ROOT:-/root/codes/ljwx-deploy}"
TEMPLATES_ROOT="${TEMPLATES_ROOT:-/root/codes/ljwx-workflow-templates}"

usage() {
  cat <<'EOF'
Usage:
  scripts/ops/scan-gitops-context.sh [options]

Options:
  --repo <path>      Target service repository path (default: current directory)
  --service <name>   Service name (default: basename of repo path)
  --skip-templates-check
                     Skip local workflow-templates path checks (for CI usage)
  --strict           Exit with code 1 if key checks are missing
  -h, --help         Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --skip-templates-check)
      SKIP_TEMPLATES_CHECK="true"
      shift
      ;;
    --strict)
      STRICT_MODE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1"
      usage
      exit 2
      ;;
  esac
done

if [[ ! -d "$REPO_PATH" ]]; then
  echo "错误: 仓库路径不存在: $REPO_PATH"
  exit 2
fi

if [[ -z "$SERVICE_NAME" ]]; then
  SERVICE_NAME="$(basename "$REPO_PATH")"
fi

MISSING_COUNT=0

ok() {
  echo "[OK] $1"
}

warn() {
  echo "[WARN] $1"
  MISSING_COUNT=$((MISSING_COUNT + 1))
}

check_path_exists() {
  local path="$1"
  local label="$2"
  if [[ -e "$path" ]]; then
    ok "$label: $path"
  else
    warn "$label 缺失: $path"
  fi
}

echo "=== GitOps Context Scan ==="
echo "repo: $REPO_PATH"
echo "service: $SERVICE_NAME"
echo

check_path_exists "$DEPLOY_ROOT" "deploy repo"
check_path_exists "$DEPLOY_ROOT/docs/START-HERE-GITOPS-ONBOARDING.md" "deploy start-here doc"

if [[ "$SKIP_TEMPLATES_CHECK" == "false" ]]; then
  check_path_exists "$TEMPLATES_ROOT" "workflow templates repo"
  check_path_exists "$TEMPLATES_ROOT/START-HERE-SERVICE-WORKFLOW.md" "workflow start-here doc"
fi

echo
echo "[1] 服务仓接入检查"

if [[ -f "$REPO_PATH/.github/workflows/build-and-enqueue.yml" ]]; then
  ok "已存在标准 workflow: .github/workflows/build-and-enqueue.yml"
elif [[ -f "$REPO_PATH/.gitea/workflows/build-and-enqueue.yml" ]]; then
  ok "已存在标准 workflow: .gitea/workflows/build-and-enqueue.yml"
else
  warn "未发现标准 build-and-enqueue workflow"
fi

if [[ -f "$REPO_PATH/.github/workflows/k3s-perf-observability.yml" ]]; then
  ok "已存在观测验证 workflow: .github/workflows/k3s-perf-observability.yml"
elif [[ -f "$REPO_PATH/.gitea/workflows/k3s-perf-observability.yml" ]]; then
  ok "已存在观测验证 workflow: .gitea/workflows/k3s-perf-observability.yml"
else
  warn "未发现 k3s-perf-observability workflow"
fi

if [[ -d "$REPO_PATH/k8s" || -d "$REPO_PATH/deploy" ]]; then
  ok "发现部署目录（k8s 或 deploy）"
else
  warn "未发现部署目录（k8s 或 deploy）"
fi

echo
echo "[2] deploy repo 映射检查"

SERVICE_MAP_FILES=(
  "$DEPLOY_ROOT/release/services.yaml"
  "$DEPLOY_ROOT/release/services.local-k3s.yaml"
  "$DEPLOY_ROOT/release/services.orbstack-k3s-cn.yaml"
)

for file in "${SERVICE_MAP_FILES[@]}"; do
  if [[ -f "$file" ]]; then
    if rg -q "^[[:space:]]{2}${SERVICE_NAME}:" "$file"; then
      ok "service map 已注册: $(basename "$file")"
    else
      warn "service map 未注册 ${SERVICE_NAME}: $(basename "$file")"
    fi
  else
    warn "service map 文件不存在: $file"
  fi
done

if command -v rg >/dev/null 2>&1; then
  if rg -q --glob '*.yaml' --glob '*.yml' "$SERVICE_NAME" "$DEPLOY_ROOT/argocd-apps" "$DEPLOY_ROOT/cluster" 2>/dev/null; then
    ok "发现 ArgoCD/cluster 侧服务引用"
  else
    warn "未发现 ArgoCD/cluster 侧服务引用"
  fi
else
  if grep -R -E -q "$SERVICE_NAME" "$DEPLOY_ROOT/argocd-apps" "$DEPLOY_ROOT/cluster" 2>/dev/null; then
    ok "发现 ArgoCD/cluster 侧服务引用"
  else
    warn "未发现 ArgoCD/cluster 侧服务引用"
  fi
fi

echo
echo "[3] 推荐动作"

if [[ "$MISSING_COUNT" -eq 0 ]]; then
  echo "状态: 已完成标准接入，无阻塞项。"
else
  echo "状态: 发现 ${MISSING_COUNT} 个缺口。"
  echo "建议先执行:"
  echo "  bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard.sh --repo \"$REPO_PATH\" --service \"$SERVICE_NAME\""
  echo "然后在 deploy repo 执行 catalog onboarding:"
  echo "  bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml dry-run"
  echo "  bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml apply"
fi

if [[ "$STRICT_MODE" == "true" && "$MISSING_COUNT" -gt 0 ]]; then
  exit 1
fi
