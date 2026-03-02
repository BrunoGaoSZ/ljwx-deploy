#!/bin/bash
# =============================================================================
# Script: create-secret.sh
# Description: 创建 ljwx-health-secret Secret
# Usage: ./create-secret.sh
# =============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认值
NAMESPACE="ljwx-health"
SECRET_NAME="ljwx-health-secret"

# 从环境变量或提示用户输入
read_secret() {
    local var_name=$1
    local prompt=$2
    local default_value=$3

    if [ -n "${!var_name}" ]; then
        echo "${!var_name}"
    elif [ -n "$default_value" ]; then
        read -p "$prompt [$default_value]: " value
        echo "${value:-$default_value}"
    else
        read -p "$prompt: " value
        echo "$value"
    fi
}

echo -e "${GREEN}=== LJWX Health Secret 创建工具 ===${NC}\n"

# 数据库配置
echo -e "${YELLOW}数据库配置（连接 infra namespace MySQL）${NC}"
DB_PASSWORD=$(read_secret "DB_PASSWORD" "数据库密码" "123456")

# Redis 配置
echo -e "\n${YELLOW}Redis 配置（连接 infra namespace Redis）${NC}"
REDIS_PASSWORD=$(read_secret "REDIS_PASSWORD" "Redis 密码" "123456")

# OSS 配置
echo -e "\n${YELLOW}OSS 配置（MinIO）${NC}"
OSS_ACCESS_KEY=$(read_secret "OSS_ACCESS_KEY" "OSS Access Key" "minioadmin")
OSS_SECRET_KEY=$(read_secret "OSS_SECRET_KEY" "OSS Secret Key" "minioadmin")

# 创建 namespace（如果不存在）
echo -e "\n${GREEN}创建 namespace: $NAMESPACE${NC}"
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# 删除旧 Secret（如果存在）
echo -e "${GREEN}删除旧 Secret（如果存在）${NC}"
kubectl delete secret $SECRET_NAME -n $NAMESPACE --ignore-not-found=true

# 创建新 Secret
echo -e "${GREEN}创建 Secret: $SECRET_NAME${NC}"
kubectl create secret generic $SECRET_NAME \
    -n $NAMESPACE \
    --from-literal=DB_PASSWORD="$DB_PASSWORD" \
    --from-literal=REDIS_PASSWORD="$REDIS_PASSWORD" \
    --from-literal=OSS_ACCESS_KEY="$OSS_ACCESS_KEY" \
    --from-literal=OSS_SECRET_KEY="$OSS_SECRET_KEY"

# 验证
echo -e "\n${GREEN}验证 Secret:${NC}"
kubectl get secret $SECRET_NAME -n $NAMESPACE

echo -e "\n${GREEN}✅ Secret 创建成功！${NC}"
echo -e "\n${YELLOW}提示：${NC}"
echo "  1. Secret 包含敏感信息，请妥善保管"
echo "  2. 数据库连接地址: mysql-infra.infra.svc.cluster.local:3306"
echo "  3. Redis 连接地址: redis-infra.infra.svc.cluster.local:6379"
echo "  4. Argo CD 应用将通过 GitOps 自动部署"
echo "  5. 访问地址: http://health-admin.omniverseai.net (HTTP)"
echo "  6. 大屏地址: http://health-dashboard.omniverseai.net (HTTP)"
