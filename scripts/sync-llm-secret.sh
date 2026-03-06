#!/bin/bash
# Sync optional OpenAI-compatible LLM settings from /root/codes/.env
# into <app-name>-llm-secret.

set -euo pipefail

APP_NAME="${1:-}"
LLM_ENV_FILE="${2:-${LLM_ENV_FILE:-/root/codes/.env}}"

if [ -z "${APP_NAME}" ]; then
    echo "错误: 请提供应用名称"
    echo "用法: $0 <app-name> [llm-env-file]"
    echo "示例: $0 ljwx-bookstore /root/codes/.env"
    exit 1
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-${APP_NAME}}"
SECRET_NAME="${SECRET_NAME:-${APP_NAME}-llm-secret}"

trim_llm_env_value() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

load_llm_env_from_file() {
    local env_file="$1"
    local raw_line=""

    export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-}"
    export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-}"
    export LLM_MODEL_FROM_ROOT_ENV="${LLM_MODEL_FROM_ROOT_ENV:-}"

    if [ ! -f "${env_file}" ]; then
        return 0
    fi

    while IFS= read -r raw_line || [ -n "$raw_line" ]; do
        local line
        local key
        local value

        line="$(trim_llm_env_value "$raw_line")"
        if [ -z "$line" ] || [ "${line#\#}" != "$line" ]; then
            continue
        fi
        if [[ "$line" == export\ * ]]; then
            line="$(trim_llm_env_value "${line#export }")"
        fi
        if [[ "$line" != *:* ]] && [[ "$line" != *=* ]]; then
            continue
        fi

        if [[ "$line" == *:* ]]; then
            key="$(trim_llm_env_value "${line%%:*}")"
            value="$(trim_llm_env_value "${line#*:}")"
        else
            key="$(trim_llm_env_value "${line%%=*}")"
            value="$(trim_llm_env_value "${line#*=}")"
        fi
        value="${value%,}"
        value="${value#\"}"
        value="${value%\"}"
        value="${value#\'}"
        value="${value%\'}"

        case "${key}" in
            ANTHROPIC_AUTH_TOKEN)
                export ANTHROPIC_AUTH_TOKEN="${value}"
                ;;
            ANTHROPIC_BASE_URL)
                export ANTHROPIC_BASE_URL="${value}"
                ;;
            model|MODEL)
                export LLM_MODEL_FROM_ROOT_ENV="${value}"
                ;;
        esac
    done < "${env_file}"
}

configure_llm_runtime_env() {
    if [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ] && [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
        export AI_LOCAL_ENABLED="${AI_LOCAL_ENABLED:-false}"
        export AI_CLOUD_ENABLED="${AI_CLOUD_ENABLED:-true}"
        export AI_CLOUD_PROVIDER="${AI_CLOUD_PROVIDER:-openai}"
        export AI_CLOUD_API_KEY="${AI_CLOUD_API_KEY:-${ANTHROPIC_AUTH_TOKEN}}"
        export AI_CLOUD_BASE_URL="${AI_CLOUD_BASE_URL:-${ANTHROPIC_BASE_URL}}"
        export AI_CLOUD_MODEL="${AI_CLOUD_MODEL:-${LLM_MODEL_FROM_ROOT_ENV:-claude-sonnet-4-6}}"

        export AI_LLM_TYPE="${AI_LLM_TYPE:-openai}"
        export AI_LLM_API_KEY="${AI_LLM_API_KEY:-${AI_CLOUD_API_KEY}}"
        export AI_LLM_BASE_URL="${AI_LLM_BASE_URL:-${AI_CLOUD_BASE_URL}}"
        export AI_LLM_MODEL="${AI_LLM_MODEL:-${AI_CLOUD_MODEL}}"
    fi
}

echo -e "${GREEN}=== 同步 ${SECRET_NAME} ===${NC}"
echo ""

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}错误: 未找到 kubectl${NC}"
    exit 1
fi

if [ ! -f "${LLM_ENV_FILE}" ]; then
    echo -e "${YELLOW}未找到 ${LLM_ENV_FILE}，跳过 ${SECRET_NAME} 同步${NC}"
    exit 0
fi

load_llm_env_from_file "${LLM_ENV_FILE}"
configure_llm_runtime_env

if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ] || [ -z "${ANTHROPIC_BASE_URL:-}" ] || [ -z "${AI_LLM_MODEL:-}" ]; then
    echo -e "${YELLOW}未在 ${LLM_ENV_FILE} 检测到完整 Claude 代理配置，跳过 ${SECRET_NAME} 同步${NC}"
    exit 0
fi

echo "已从 ${LLM_ENV_FILE} 加载 LLM 配置"
echo "  provider: ${AI_LLM_TYPE}"
echo "  base_url: ${AI_LLM_BASE_URL}"
echo "  model: ${AI_LLM_MODEL}"
echo ""

if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    echo -e "${YELLOW}namespace ${NAMESPACE} 不存在，创建中...${NC}"
    kubectl create namespace "${NAMESPACE}"
fi

kubectl create secret generic "${SECRET_NAME}" \
  --from-literal=AI_LOCAL_ENABLED="${AI_LOCAL_ENABLED}" \
  --from-literal=AI_CLOUD_ENABLED="${AI_CLOUD_ENABLED}" \
  --from-literal=AI_CLOUD_PROVIDER="${AI_CLOUD_PROVIDER}" \
  --from-literal=AI_CLOUD_API_KEY="${AI_CLOUD_API_KEY}" \
  --from-literal=AI_CLOUD_BASE_URL="${AI_CLOUD_BASE_URL}" \
  --from-literal=AI_CLOUD_MODEL="${AI_CLOUD_MODEL}" \
  --from-literal=AI_LLM_TYPE="${AI_LLM_TYPE}" \
  --from-literal=AI_LLM_API_KEY="${AI_LLM_API_KEY}" \
  --from-literal=AI_LLM_BASE_URL="${AI_LLM_BASE_URL}" \
  --from-literal=AI_LLM_MODEL="${AI_LLM_MODEL}" \
  --from-literal=ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN}" \
  --from-literal=ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL}" \
  --namespace="${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo -e "${GREEN}✓ 已更新 Secret ${SECRET_NAME}${NC}"
