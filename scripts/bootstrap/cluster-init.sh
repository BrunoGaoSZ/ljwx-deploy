#!/usr/bin/env bash

set -euo pipefail

# This script bootstraps a cluster using Git-managed Argo applications.

ENV_NAME=""
PROFILE_NAME=""
APPLY_MODE="false"
SKIP_TLS="false"

usage() {
  cat <<'EOF'
用法:
  bash scripts/bootstrap/cluster-init.sh --env <env> --profile <profile> [--apply] [--skip-tls]

示例:
  bash scripts/bootstrap/cluster-init.sh --env dev --profile local-k3s
  bash scripts/bootstrap/cluster-init.sh --env dev --profile local-k3s --apply
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_NAME="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE_NAME="${2:-}"
      shift 2
      ;;
    --apply)
      APPLY_MODE="true"
      shift
      ;;
    --skip-tls)
      SKIP_TLS="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$ENV_NAME" || -z "$PROFILE_NAME" ]]; then
  echo "必须同时提供 --env 和 --profile。" >&2
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_MATRIX="$REPO_ROOT/platform/assembly/env-matrix.yaml"
ARGO_CLUSTER_BOOTSTRAP="$REPO_ROOT/argocd-apps/00-cluster-bootstrap.yaml"
ARGO_APPS_BOOTSTRAP="$REPO_ROOT/argocd-apps/01-apps-bootstrap.yaml"
TLS_APP="$REPO_ROOT/argocd-apps/03-cert-manager-dev.yaml"
TLS_CONFIG_APP="$REPO_ROOT/argocd-apps/04-cert-manager-config-dev.yaml"

for required_file in \
  "$ENV_MATRIX" \
  "$ARGO_CLUSTER_BOOTSTRAP" \
  "$ARGO_APPS_BOOTSTRAP"; do
  if [[ ! -f "$required_file" ]]; then
    echo "缺少必需文件: $required_file" >&2
    exit 1
  fi
done

echo "准备初始化集群。"
echo "环境: $ENV_NAME"
echo "Profile: $PROFILE_NAME"
echo "应用模式: $APPLY_MODE"
echo "跳过 TLS: $SKIP_TLS"

echo "校验完成，计划执行以下步骤："
echo "1. 应用 cluster bootstrap Argo app"
echo "2. 应用 apps bootstrap Argo app"
if [[ "$SKIP_TLS" != "true" ]]; then
  echo "3. 应用 cert-manager 与 TLS 配置"
fi
echo "4. 等待 Argo 接管后续资源"
echo "5. 运行 smoke 和证据校验"

if [[ "$APPLY_MODE" != "true" ]]; then
  echo "当前为预览模式，未执行 kubectl apply。"
  exit 0
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "未找到 kubectl，无法执行 apply。" >&2
  exit 1
fi

echo "开始应用 Argo bootstrap 资源。"
kubectl apply -f "$ARGO_CLUSTER_BOOTSTRAP"
kubectl apply -f "$ARGO_APPS_BOOTSTRAP"

if [[ "$SKIP_TLS" != "true" ]]; then
  kubectl apply -f "$TLS_APP"
  kubectl apply -f "$TLS_CONFIG_APP"
fi

echo "初始化命令已执行。请随后检查 Argo、Smoke 和 Evidence 状态。"
