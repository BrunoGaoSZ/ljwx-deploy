# ljwx-bookstore Secret 管理

## 概述

为了符合安全最佳实践和GitOps原则，ljwx-bookstore的Secret**不在Git中存储**。

## Secret 创建方式

### 自动化脚本（推荐）

使用提供的脚本从infra namespace自动获取密码并创建Secret：

```bash
# 在 ljwx-deploy 仓库根目录执行
./scripts/create-app-secret.sh ljwx-bookstore
```

### 手动创建

如果自动化脚本不可用，使用以下命令手动创建：

```bash
# 从 infra namespace 获取基础设施密码
MYSQL_PASSWORD=$(kubectl get secret infra-credentials -n infra -o jsonpath='{.data.mysql-root-password}' | base64 -d)
REDIS_PASSWORD=$(kubectl get secret infra-credentials -n infra -o jsonpath='{.data.redis-password}' | base64 -d)

# 创建 ljwx-bookstore Secret
kubectl create secret generic ljwx-bookstore-secret \
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
  --namespace=ljwx-bookstore
```

## Secret 架构

```
┌─────────────────────────────────────┐
│ infra namespace                     │
│ ┌─────────────────────────────────┐ │
│ │ infra-credentials Secret        │ │  ← 唯一真实来源
│ │ - mysql-root-password           │ │    (infra团队管理)
│ │ - redis-password                │ │
│ │ - postgres-password             │ │
│ └─────────────────────────────────┘ │
└──────────────┬──────────────────────┘
               │
               │ 手动复制密码
               │ (未来: External Secrets Operator自动同步)
               ▼
┌─────────────────────────────────────┐
│ ljwx-bookstore namespace            │
│ ┌─────────────────────────────────┐ │
│ │ ljwx-bookstore-secret           │ │  ← 手动创建（一次性）
│ │ - DB_PASSWORD (从infra复制)     │ │
│ │ - REDIS_PASSWORD (从infra复制)  │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

## 部署流程

### 新环境部署

1. **创建 infra namespace 基础设施密码**（infra团队负责）
   ```bash
   kubectl create secret generic infra-credentials \
     --from-literal=mysql-root-password='YOUR_PASSWORD' \
     --from-literal=redis-password='YOUR_PASSWORD' \
     --namespace=infra
   ```

2. **创建应用 Secret**
   ```bash
   ./scripts/create-app-secret.sh ljwx-bookstore
   ```

3. **部署应用**（Argo CD自动同步）
   ```bash
   argocd app sync ljwx-bookstore
   ```

### 密码轮换

当infra团队更新基础设施密码时：

```bash
# 1. infra团队更新 infra-credentials
kubectl patch secret infra-credentials -n infra \
  --type='json' \
  -p='[{"op": "replace", "path": "/data/mysql-root-password", "value": "BASE64_NEW_PASSWORD"}]'

# 2. 重新创建应用Secret
kubectl delete secret ljwx-bookstore-secret -n ljwx-bookstore
./scripts/create-app-secret.sh ljwx-bookstore

# 3. 重启应用
kubectl rollout restart deployment ljwx-bookstore -n ljwx-bookstore
```

## 验证

```bash
# 检查Secret是否存在
kubectl get secret ljwx-bookstore-secret -n ljwx-bookstore

# 验证密码值
kubectl get secret ljwx-bookstore-secret -n ljwx-bookstore \
  -o jsonpath='{.data.DB_PASSWORD}' | base64 -d

# 应该输出与infra-credentials中相同的密码
```

## 路线图

**当前状态**（过渡方案）:
- ✅ Secret不在Git中（符合安全最佳实践）
- ✅ 使用脚本从infra统一获取密码（避免手动输入错误）
- ⚠️ 需要手动创建一次Secret

**未来计划**（完全GitOps）:
- [ ] 部署 External Secrets Operator
- [ ] 迁移到 ExternalSecret CRD
- [ ] 实现自动密码同步
- [ ] 无需任何手动操作

## 故障排查

### Secret未找到

```bash
# 检查Secret是否存在
kubectl get secret ljwx-bookstore-secret -n ljwx-bookstore

# 如果不存在，创建它
./scripts/create-app-secret.sh ljwx-bookstore
```

### 密码不正确

```bash
# 比较应用Secret和infra Secret
echo "infra密码:"
kubectl get secret infra-credentials -n infra -o jsonpath='{.data.mysql-root-password}' | base64 -d

echo ""
echo "应用密码:"
kubectl get secret ljwx-bookstore-secret -n ljwx-bookstore -o jsonpath='{.data.DB_PASSWORD}' | base64 -d

# 如果不一致，重新创建
kubectl delete secret ljwx-bookstore-secret -n ljwx-bookstore
./scripts/create-app-secret.sh ljwx-bookstore
```

## 相关文档

- 详细架构设计：`/docs/GITOPS_SECRET_MANAGEMENT.md`
- infra namespace密码管理：`/infra/secrets/README.md`
