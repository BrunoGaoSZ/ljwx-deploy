#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RUNTIME_CHECK="false"
POSTGRES_NS="${POSTGRES_NS:-infra}"
POSTGRES_POD="${POSTGRES_POD:-postgres-0}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
CHAT_DB="${CHAT_DB:-ljwx_chat}"

usage() {
  cat <<'EOF'
Usage:
  scripts/ops/check-pgvector.sh [--runtime]

Options:
  --runtime   Also validate runtime state in k3s cluster
  -h, --help  Show help

Environment variables (for --runtime):
  POSTGRES_NS    default: infra
  POSTGRES_POD   default: postgres-0
  POSTGRES_USER  default: postgres
  CHAT_DB        default: ljwx_chat
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime)
      RUNTIME_CHECK="true"
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

ok() {
  echo "[OK] $1"
}

fail() {
  echo "[FAIL] $1"
  exit 1
}

must_file() {
  local f="$1"
  [[ -f "$f" ]] || fail "文件不存在: $f"
}

DATA_KUSTOM="$ROOT_DIR/infra/data/kustomization.yaml"
PG_STS="$ROOT_DIR/infra/postgres/statefulset.yaml"

must_file "$DATA_KUSTOM"
must_file "$PG_STS"

if ! grep -Eq '^[[:space:]]*-[[:space:]]+\.\./postgres[[:space:]]*$' "$DATA_KUSTOM"; then
  fail "infra/data 未引用 ../postgres，infra-data 将无法托管 postgres"
fi
ok "infra/data 已引用 ../postgres"

if ! grep -Eq '^[[:space:]]*-[[:space:]]+\.\./redis[[:space:]]*$' "$DATA_KUSTOM"; then
  fail "infra/data 未引用 ../redis，infra-data 将无法托管 redis"
fi
ok "infra/data 已引用 ../redis"

if ! grep -Eq '^[[:space:]]*image:[[:space:]]*pgvector/pgvector:pg16([._-][[:alnum:]]+)?[[:space:]]*$' "$PG_STS"; then
  fail "infra/postgres 未使用 pgvector/pgvector:pg16 镜像，ljwx-chat 可能因 vector 扩展缺失而崩溃"
fi
ok "infra/postgres 镜像满足 pgvector 要求"

if [[ "$RUNTIME_CHECK" != "true" ]]; then
  echo "静态检查通过。"
  exit 0
fi

command -v kubectl >/dev/null 2>&1 || fail "未找到 kubectl，无法执行运行时检查"

kubectl -n "$POSTGRES_NS" get pod "$POSTGRES_POD" >/dev/null 2>&1 || fail "未找到 Pod: ${POSTGRES_NS}/${POSTGRES_POD}"
ok "运行时 Pod 存在: ${POSTGRES_NS}/${POSTGRES_POD}"

RUNTIME_IMAGE="$(kubectl -n "$POSTGRES_NS" get sts postgres -o jsonpath='{.spec.template.spec.containers[?(@.name=="postgres")].image}')"
if [[ ! "$RUNTIME_IMAGE" =~ ^pgvector/pgvector:pg16 ]]; then
  fail "运行时 postgres 镜像不是 pgvector/pgvector:pg16，当前: ${RUNTIME_IMAGE}"
fi
ok "运行时 postgres 镜像已对齐: ${RUNTIME_IMAGE}"

EXT_NAME="$(
  kubectl -n "$POSTGRES_NS" exec "$POSTGRES_POD" -- \
    psql -U "$POSTGRES_USER" -d "$CHAT_DB" -tAc "SELECT extname FROM pg_extension WHERE extname='vector';" \
    | tr -d '[:space:]'
)"
if [[ "$EXT_NAME" != "vector" ]]; then
  fail "运行时数据库 ${CHAT_DB} 未检测到 vector 扩展"
fi
ok "运行时数据库 ${CHAT_DB} 已启用 vector 扩展"

echo "运行时检查通过。"
