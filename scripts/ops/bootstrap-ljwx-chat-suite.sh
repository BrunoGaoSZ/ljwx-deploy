#!/usr/bin/env bash
set -euo pipefail

# Bootstrap shared dependencies for ljwx-website / ljwx-dify / ljwx-chat.

DIFY_NS="${DIFY_NS:-ljwx-dify-dev}"
CHAT_NS="${CHAT_NS:-ljwx-chat-dev}"
WEBSITE_NS="${WEBSITE_NS:-ljwx-website-dev}"

DIFY_ADMIN_EMAIL="${DIFY_ADMIN_EMAIL:-admin@lingjingwanxiang.cn}"
DIFY_ADMIN_NAME="${DIFY_ADMIN_NAME:-管理员}"
DIFY_ADMIN_PASSWORD="${DIFY_ADMIN_PASSWORD:-}"
DIFY_INIT_PASSWORD="${DIFY_INIT_PASSWORD:-}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
CHAT_OPENCLAW_GATEWAY_TOKEN="${CHAT_OPENCLAW_GATEWAY_TOKEN:-${CHAT_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}}"
CHAT_OPENCLAW_GATEWAY_URL="${CHAT_OPENCLAW_GATEWAY_URL:-https://openclaw.lingjingwanxiang.cn/v1}"
CHAT_OPENCLAW_GATEWAY_ORIGIN="${CHAT_OPENCLAW_GATEWAY_ORIGIN:-https://openclaw.lingjingwanxiang.cn}"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "错误: 缺少命令 $cmd"
    exit 1
  fi
}

require_cmd kubectl
require_cmd openssl
require_cmd base64
require_cmd jq

if ! kubectl get ns infra >/dev/null 2>&1; then
  echo "错误: 未找到 infra 命名空间，无法复用共享 Postgres/Redis/MinIO"
  exit 1
fi

echo "[1/7] 创建目标命名空间..."
kubectl create ns "$DIFY_NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl create ns "$CHAT_NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl create ns "$WEBSITE_NS" --dry-run=client -o yaml | kubectl apply -f -

echo "[2/7] 读取 infra 共享凭据..."
POSTGRES_USER="$(kubectl -n infra get secret postgres-admin -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)"
POSTGRES_PASSWORD="$(kubectl -n infra get secret postgres-admin -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)"
REDIS_PASSWORD="$(kubectl -n infra get secret redis-secret -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)"
MINIO_USER="$(kubectl -n infra get secret minio-secret -o jsonpath='{.data.MINIO_ROOT_USER}' | base64 -d)"
MINIO_PASSWORD="$(kubectl -n infra get secret minio-secret -o jsonpath='{.data.MINIO_ROOT_PASSWORD}' | base64 -d)"

echo "[3/7] 同步镜像拉取凭据 (regcred)..."
if kubectl -n infra get secret regcred >/dev/null 2>&1; then
  for ns in "$DIFY_NS" "$CHAT_NS" "$WEBSITE_NS"; do
    kubectl -n infra get secret regcred -o json \
      | jq "del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.namespace,.metadata.annotations,.metadata.managedFields) | .metadata.name=\"regcred\" | .metadata.namespace=\"${ns}\"" \
      | kubectl apply -f -
  done
else
  echo "警告: infra/regcred 不存在，私有镜像拉取可能失败"
fi

echo "[4/7] 初始化数据库..."
for db in ljwx_dify ljwx_chat; do
  kubectl -n infra exec statefulset/postgres -- sh -lc \
    "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U '${POSTGRES_USER}' -d postgres -v ON_ERROR_STOP=1 -c \"CREATE DATABASE ${db};\"" \
    >/dev/null 2>&1 || true
done

if [[ -z "$DIFY_ADMIN_PASSWORD" ]]; then
  echo "错误: 未设置 DIFY_ADMIN_PASSWORD，无法自动登录 Dify 控制台配置默认模型"
  exit 1
fi

if [[ -z "$ANTHROPIC_API_KEY" ]]; then
  echo "错误: 未设置 ANTHROPIC_API_KEY，无法写入 Anthropic Provider 凭据"
  exit 1
fi

echo "[5/7] 同步 ljwx-dify secret..."
DIFY_SECRET_KEY="$(openssl rand -hex 32)"
DIFY_PLUGIN_KEY="$(openssl rand -hex 32)"
DIFY_INNER_KEY="$(openssl rand -hex 32)"
DIFY_QDRANT_KEY="$(openssl rand -hex 24)"

kubectl -n "$DIFY_NS" create secret generic ljwx-dify-secrets \
  --from-literal=DB_USERNAME="$POSTGRES_USER" \
  --from-literal=DB_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=REDIS_PASSWORD="$REDIS_PASSWORD" \
  --from-literal=CELERY_BROKER_URL="redis://:${REDIS_PASSWORD}@redis-lb.infra.svc.cluster.local:6379/1" \
  --from-literal=SECRET_KEY="$DIFY_SECRET_KEY" \
  --from-literal=PLUGIN_DAEMON_KEY="$DIFY_PLUGIN_KEY" \
  --from-literal=DIFY_INNER_API_KEY="$DIFY_INNER_KEY" \
  --from-literal=QDRANT_API_KEY="$DIFY_QDRANT_KEY" \
  --from-literal=DIFY_ADMIN_EMAIL="$DIFY_ADMIN_EMAIL" \
  --from-literal=DIFY_ADMIN_NAME="$DIFY_ADMIN_NAME" \
  --from-literal=DIFY_ADMIN_PASSWORD="$DIFY_ADMIN_PASSWORD" \
  --from-literal=DIFY_INIT_PASSWORD="$DIFY_INIT_PASSWORD" \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --from-literal=ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
  --from-literal=S3_ACCESS_KEY="$MINIO_USER" \
  --from-literal=S3_SECRET_KEY="$MINIO_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "[6/7] 同步 ljwx-chat secret..."
CHAT_KEY_VAULTS_SECRET="$(openssl rand -base64 32 | tr -d '\n')"
CHAT_NEXTAUTH_SECRET="$(openssl rand -base64 32 | tr -d '\n')"
CHAT_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres-lb.infra.svc.cluster.local:5432/ljwx_chat"

chat_secret_args=(
  --from-literal=DATABASE_URL="$CHAT_DATABASE_URL" \
  --from-literal=KEY_VAULTS_SECRET="$CHAT_KEY_VAULTS_SECRET" \
  --from-literal=NEXTAUTH_SECRET="$CHAT_NEXTAUTH_SECRET" \
  --from-literal=NEXT_AUTH_SECRET="$CHAT_NEXTAUTH_SECRET" \
  --from-literal=S3_ENDPOINT="http://minio.infra.svc.cluster.local:9000" \
  --from-literal=S3_PUBLIC_DOMAIN="https://s3.lingjingwanxiang.cn" \
  --from-literal=S3_ACCESS_KEY_ID="$MINIO_USER" \
  --from-literal=S3_SECRET_ACCESS_KEY="$MINIO_PASSWORD" \
  --from-literal=REDIS_URL="redis://:${REDIS_PASSWORD}@redis-lb.infra.svc.cluster.local:6379/0"
)

if [[ -n "$CHAT_OPENCLAW_GATEWAY_TOKEN" ]]; then
  chat_secret_args+=(
    --from-literal=OPENAI_API_KEY="$CHAT_OPENCLAW_GATEWAY_TOKEN" \
    --from-literal=OPENCLAW_GATEWAY_TOKEN="$CHAT_OPENCLAW_GATEWAY_TOKEN"
  )
else
  echo "警告: 未设置 CHAT_OPENCLAW_GATEWAY_TOKEN/CHAT_OPENAI_API_KEY/OPENAI_API_KEY，ljwx-chat 将无法通过 OpenClaw 调用模型"
fi

kubectl -n "$CHAT_NS" create secret generic ljwx-chat-secrets \
  "${chat_secret_args[@]}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "[7/7] 完成。现在可执行 GitOps/清单部署。"
echo "- 命名空间: $DIFY_NS, $CHAT_NS, $WEBSITE_NS"
echo "- 数据库: ljwx_dify, ljwx_chat"
echo "- ljwx-chat OpenClaw gateway: $CHAT_OPENCLAW_GATEWAY_URL"
echo "- ljwx-chat OpenClaw origin: $CHAT_OPENCLAW_GATEWAY_ORIGIN"
