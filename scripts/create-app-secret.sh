#!/bin/bash
# =============================================================================
# 从 infra namespace 创建应用 Secret
# 用法: ./create-app-secret.sh <app-name>
# 示例: ./create-app-secret.sh ljwx-bookstore
# =============================================================================

set -e

APP_NAME="${1}"

if [ -z "$APP_NAME" ]; then
    echo "错误: 请提供应用名称"
    echo "用法: $0 <app-name>"
    echo "示例: $0 ljwx-bookstore"
    exit 1
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== 为 ${APP_NAME} 创建 Secret ===${NC}"
echo ""

# =============================================================================
# 检查 infra-credentials 是否存在
# =============================================================================
if ! kubectl get secret infra-credentials -n infra &>/dev/null; then
    echo -e "${RED}错误: infra-credentials Secret 不存在于 infra namespace${NC}"
    echo ""
    echo "请先创建 infra-credentials Secret:"
    echo "  kubectl create secret generic infra-credentials \\"
    echo "    --from-literal=mysql-root-password='YOUR_PASSWORD' \\"
    echo "    --from-literal=redis-password='YOUR_PASSWORD' \\"
    echo "    --from-literal=postgres-password='YOUR_PASSWORD' \\"
    echo "    --namespace=infra"
    exit 1
fi

# =============================================================================
# 从 infra namespace 获取密码
# =============================================================================
echo -e "${YELLOW}从 infra namespace 获取基础设施密码...${NC}"

MYSQL_PASSWORD=$(kubectl get secret infra-credentials -n infra -o jsonpath='{.data.mysql-root-password}' | base64 -d)
REDIS_PASSWORD=$(kubectl get secret infra-credentials -n infra -o jsonpath='{.data.redis-password}' | base64 -d)

if [ -z "$MYSQL_PASSWORD" ] || [ -z "$REDIS_PASSWORD" ]; then
    echo -e "${RED}错误: 无法从 infra-credentials 获取密码${NC}"
    exit 1
fi

echo "✓ MySQL密码: ${MYSQL_PASSWORD:0:3}***"
echo "✓ Redis密码: ${REDIS_PASSWORD:0:3}***"
echo ""

# =============================================================================
# 检查 namespace 是否存在
# =============================================================================
if ! kubectl get namespace "$APP_NAME" &>/dev/null; then
    echo -e "${YELLOW}namespace ${APP_NAME} 不存在，创建中...${NC}"
    kubectl create namespace "$APP_NAME"
    echo "✓ namespace ${APP_NAME} 创建成功"
    echo ""
fi

# =============================================================================
# 创建 Secret
# =============================================================================
echo -e "${YELLOW}创建 ${APP_NAME}-secret...${NC}"

kubectl create secret generic "${APP_NAME}-secret" \
  --from-literal=DB_HOST='mysql-infra.infra.svc.cluster.local' \
  --from-literal=DB_PORT='3306' \
  --from-literal=DB_NAME='org_fiction' \
  --from-literal=DB_USER='root' \
  --from-literal=DB_PASSWORD="${MYSQL_PASSWORD}" \
  --from-literal=REDIS_HOST='redis-infra-master.infra.svc.cluster.local' \
  --from-literal=REDIS_PORT='6379' \
  --from-literal=REDIS_PASSWORD="${REDIS_PASSWORD}" \
  --from-literal=WX_APP_SECRET="placeholder" \
  --from-literal=WX_MCH_KEY="placeholder" \
  --from-literal=MAIL_PASSWORD="placeholder" \
  --from-literal=SMS_TENCENT_APPKEY="placeholder" \
  --from-literal=SMS_ALIYUN_ACCESS_KEY_SECRET="xxx" \
  --from-literal=STORAGE_ALIYUN_ACCESS_KEY_ID="placeholder" \
  --from-literal=STORAGE_ALIYUN_ACCESS_KEY_SECRET="placeholder" \
  --from-literal=STORAGE_TENCENT_SECRET_ID="placeholder" \
  --from-literal=STORAGE_TENCENT_SECRET_KEY="placeholder" \
  --from-literal=AI_CLOUD_API_KEY="" \
  --namespace="${APP_NAME}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✓ Secret ${APP_NAME}-secret 创建成功"
echo ""

# =============================================================================
# 验证
# =============================================================================
echo -e "${YELLOW}验证 Secret...${NC}"

kubectl get secret "${APP_NAME}-secret" -n "${APP_NAME}" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ Secret 存在"

    # 验证密码值
    APP_DB_PASSWORD=$(kubectl get secret "${APP_NAME}-secret" -n "${APP_NAME}" -o jsonpath='{.data.DB_PASSWORD}' | base64 -d)
    if [ "$APP_DB_PASSWORD" == "$MYSQL_PASSWORD" ]; then
        echo "✓ 数据库密码验证成功"
    else
        echo -e "${RED}⚠ 警告: 数据库密码不匹配${NC}"
    fi
else
    echo -e "${RED}✗ Secret 创建失败${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}=== 完成！ ===${NC}"
echo ""
echo "下一步:"
echo "  1. 触发 Argo CD 同步: argocd app sync ${APP_NAME}"
echo "  2. 检查应用状态: kubectl get pods -n ${APP_NAME}"
echo ""
