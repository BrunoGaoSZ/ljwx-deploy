# ljwx-template GitOps 配置

此目录包含 ljwx-template 项目的 GitOps 部署配置，配合 Argo CD 使用。

## 架构说明

### 仓库分离策略

**代码仓库** (`ljwx-template`)：
- 业务代码（FastAPI + Spring Boot）
- Helm Chart (`deploy/helm/app/`)
- CI Pipeline（GitHub Actions）

**GitOps 仓库** (`ljwx-deploy` - 本仓库)：
- Argo CD Application 定义
- 环境特定配置
- AppProject 权限定义

**优势**：
- ✅ 权限分离：开发人员无需访问部署配置
- ✅ 审批独立：部署变更有独立的 PR 流程
- ✅ 回滚清晰：部署配置历史独立管理
- ✅ 安全性高：Secrets 不在代码仓库

## 目录结构

```
apps/ljwx-template/
├── base/
│   └── values-common.yaml      # 所有环境共享配置
└── overlays/
    ├── eu-dev/
    │   └── values.yaml          # EU Dev 环境配置
    ├── mac-dev/
    │   └── values.yaml          # Mac Dev 环境配置
    └── prod/
        └── values.yaml          # 生产环境配置
```

## 配置覆盖顺序

Argo CD 会按以下顺序合并配置：

1. **Helm Chart 默认值** (`ljwx-template/deploy/helm/app/values.yaml`)
2. **通用配置** (`base/values-common.yaml`)
3. **环境特定配置** (`overlays/{env}/values.yaml`)

后面的配置会覆盖前面的。

## 环境说明

### EU Dev (`overlays/eu-dev/`)
- **用途**: EU 团队开发环境
- **命名空间**: `dev`
- **特点**: DEBUG 日志，1 副本，资源限制较小

### Mac Dev (`overlays/mac-dev/`)
- **用途**: Mac k3s 本地开发环境
- **命名空间**: `dev`
- **特点**: DEBUG 日志，1 副本，本地数据库

### Prod (`overlays/prod/`)
- **用途**: 生产环境
- **命名空间**: `ljwx-template-prod`
- **特点**: INFO 日志，3 副本，HPA，HTTPS Ingress

## 使用方法

### 修改配置

1. 克隆本仓库：
```bash
git clone git@github.com:BrunoGaoSZ/ljwx-deploy.git
cd ljwx-deploy/apps/ljwx-template
```

2. 编辑环境特定配置：
```bash
# 修改 EU Dev 配置
vim overlays/eu-dev/values.yaml

# 例如：调整副本数
# apiFast:
#   replicaCount: 2
```

3. 提交变更：
```bash
git add .
git commit -m "feat(ljwx-template): increase eu-dev replicas to 2"
git push
```

4. Argo CD 自动检测变更并部署（~30 秒）

### 查看部署状态

```bash
# CLI
argocd app get ljwx-template-eu-dev

# Web UI
open https://argocd.example.com
```

### 回滚配置

```bash
# Git 回滚
git revert HEAD
git push

# 或使用 Argo CD 回滚
argocd app rollback ljwx-template-eu-dev
```

## 常见配置修改

### 1. 调整资源限制

```yaml
# overlays/eu-dev/values.yaml
apiFast:
  resources:
    requests:
      memory: "512Mi"  # 从 128Mi 提升
      cpu: "500m"      # 从 100m 提升
    limits:
      memory: "1Gi"
      cpu: "1000m"
```

### 2. 更新镜像版本

```yaml
# overlays/eu-dev/values.yaml
apiFast:
  image:
    tag: "main-abc1234"  # 使用特定 Git SHA
```

### 3. 启用 HPA

```yaml
# overlays/eu-dev/values.yaml
apiFast:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 5
    targetCPUUtilizationPercentage: 70
```

### 4. 更新数据库连接

```yaml
# overlays/eu-dev/values.yaml
database:
  host: new-postgres-host.example.com
  port: 5432
  name: new_database
```

### 5. 修改日志级别

```yaml
# overlays/prod/values.yaml
apiFast:
  env:
    LOG_LEVEL: "WARNING"  # 从 INFO 调整为 WARNING
```

## 安全最佳实践

### 1. Secrets 管理

**禁止在 Git 中存储 Secrets！**

使用以下方案之一：
- **ExternalSecrets Operator** (推荐)
- **SealedSecrets**
- **Vault**
- 手动创建 K8s Secrets

示例（ExternalSecrets）：
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-credentials-eu-dev
spec:
  secretStoreRef:
    name: vault-backend
  target:
    name: db-credentials-eu-dev
  data:
    - secretKey: DB_USER
      remoteRef:
        key: ljwx/eu-dev/database
        property: username
```

### 2. 权限控制

- 使用 `ljwx:developer` 角色：只读权限
- 使用 `ljwx:operator` 角色：同步权限
- 生产环境需要额外审批

### 3. 变更审计

所有变更都通过 Git PR：
- 需要 Code Review
- 自动触发 CI 检查
- 可追溯历史

## 故障排查

### Application 无法同步

```bash
# 查看详细状态
argocd app get ljwx-template-eu-dev

# 查看差异
argocd app diff ljwx-template-eu-dev

# 强制刷新
argocd app sync ljwx-template-eu-dev --force
```

### 配置未生效

检查配置覆盖顺序：
```bash
# 查看最终渲染的 manifest
argocd app manifests ljwx-template-eu-dev
```

### PreSync Hook 失败

查看 Migration Job 日志：
```bash
kubectl logs -n dev job/ljwx-template-migration-xxx
```

## 相关文档

- **代码仓库**: https://github.com/BrunoGaoSZ/ljwx-template
- **Helm Chart 说明**: `ljwx-template/deploy/helm/app/README.md`
- **完整部署指南**: `ljwx-template/deploy/argo/README.md`
- **Argo CD 官方文档**: https://argo-cd.readthedocs.io/

## 联系方式

- 问题反馈: https://github.com/BrunoGaoSZ/ljwx-template/issues
- 团队: ljwx-team@example.com
