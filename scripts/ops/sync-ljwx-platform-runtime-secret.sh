#!/usr/bin/env bash
set -euo pipefail

NS="${1:-ljwx-platform}"
DB_SECRET_NAME="${2:-ljwx-platform-db}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "错误: 未找到 kubectl"
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "错误: 未找到 openssl"
  exit 1
fi

if ! kubectl -n infra get secret postgres-admin >/dev/null 2>&1; then
  echo "错误: infra 命名空间缺少 secret/postgres-admin"
  exit 1
fi

if ! kubectl -n infra get secret redis-secret >/dev/null 2>&1; then
  echo "错误: infra 命名空间缺少 secret/redis-secret"
  exit 1
fi

kubectl get ns "${NS}" >/dev/null 2>&1 || kubectl create ns "${NS}" >/dev/null

DB_USERNAME="$(kubectl -n infra get secret postgres-admin -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)"
DB_PASSWORD="$(kubectl -n infra get secret postgres-admin -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)"
REDIS_PASSWORD="$(kubectl -n infra get secret redis-secret -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)"
JWT_SECRET="$(openssl rand -hex 32)"

kubectl -n "${NS}" create secret generic "${DB_SECRET_NAME}" \
  --from-literal=DB_USERNAME="${DB_USERNAME}" \
  --from-literal=DB_PASSWORD="${DB_PASSWORD}" \
  --from-literal=REDIS_PASSWORD="${REDIS_PASSWORD}" \
  --from-literal=JWT_SECRET="${JWT_SECRET}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "已同步 secret/${DB_SECRET_NAME} 到命名空间 ${NS}"
