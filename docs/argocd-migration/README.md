# ArgoCD PreSync Hook - 数据库迁移

## 📋 概述

本文档说明如何在 ArgoCD 中使用 **PreSync Hook** 自动执行数据库迁移。

**工作流程：**
```
1. git push → CI 构建镜像
2. CI 更新 GitOps 仓库
3. ArgoCD 检测到变化
4. 执行 PreSync Hook（数据库迁移）
   ✓ 成功 → 继续部署应用
   ✗ 失败 → 阻止部署
5. 部署新版本应用
```

---

## 🎯 PreSync Hook 机制

### Hook 类型

| Hook | 执行时机 | 用途 |
|------|---------|------|
| **PreSync** | 同步前 | 数据库迁移、配置预检 |
| Sync | 同步中 | 标准资源部署 |
| PostSync | 同步后 | 数据初始化、通知 |
| SyncFail | 失败时 | 清理、回滚、告警 |

### PreSync 注解

```yaml
metadata:
  annotations:
    # 标记为 PreSync Hook
    argocd.argoproj.io/hook: PreSync

    # 删除策略：在新 Hook 执行前删除旧的
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation

    # Sync Wave：-1 表示最先执行
    argocd.argoproj.io/sync-wave: "-1"
```

---

## 📁 文件组织

### 方式 1：ConfigMap（适合少量迁移）

```yaml
# 迁移文件存储在 ConfigMap
apps/youngth-guard/overlays/dev/
├── db-migrations-configmap.yaml  # 包含 SQL 文件
└── db-migration-job.yaml          # PreSync Job
```

**优点：** 简单直接
**缺点：** ConfigMap 大小限制 1MB，不适合大量迁移

### 方式 2：打包到镜像（推荐）

```dockerfile
# Dockerfile
FROM flyway/flyway:10-alpine

# 复制迁移文件
COPY backend-fastapi/migrations /flyway/sql

# 复制配置
COPY flyway.conf /flyway/conf/
```

**优点：**
- 迁移文件和代码版本一致
- 无大小限制
- 便于审计

**缺点：** 需要构建专门的迁移镜像

### 方式 3：从 Git 拉取（灵活）

```yaml
initContainers:
  - name: fetch-migrations
    image: alpine/git
    command:
      - /bin/sh
      - -c
      - |
        git clone --depth=1 --branch=main \
          https://github.com/BrunoGaoSZ/youngth-guard.git /repo
        cp -r /repo/backend-fastapi/migrations/* /migrations/
    volumeMounts:
      - name: migrations
        mountPath: /migrations
```

**优点：**
- 灵活，可以指定 branch/tag
- 不需要重新构建镜像

**缺点：**
- 需要 Git 访问权限
- 依赖外部服务

---

## 🔒 并发保护

### 问题：多个 Sync 同时触发

如果多个开发者同时部署，可能导致多个迁移 Job 并发执行。

### 解决方案：Flyway 内置锁

Flyway 使用数据库表锁防止并发：

```sql
-- Flyway 自动创建的锁表
CREATE TABLE flyway_schema_history (
    installed_rank INT NOT NULL,
    version VARCHAR(50),
    description VARCHAR(200),
    type VARCHAR(20),
    script VARCHAR(1000),
    checksum INT,
    installed_by VARCHAR(100),
    installed_on TIMESTAMP DEFAULT NOW(),
    execution_time INT,
    success BOOLEAN NOT NULL,
    PRIMARY KEY (installed_rank)
);

-- 执行迁移时 Flyway 会锁定此表
```

**机制：**
1. Job A 开始迁移 → 锁定 `flyway_schema_history`
2. Job B 尝试迁移 → 等待锁释放（超时后失败）
3. Job A 完成 → 释放锁
4. Job B 检测到已执行，跳过

### 额外保护：BackoffLimit

```yaml
spec:
  backoffLimit: 0  # 失败后不重试
```

避免失败后反复重试导致资源浪费。

---

## ❌ 失败路径说明

### 场景 1：迁移 SQL 错误

```
PreSync Job 失败 (Exit Code 1)
  ↓
ArgoCD 标记 Sync 失败
  ↓
应用部署被阻止（Deployment 不会更新）
  ↓
旧版本应用继续运行
```

**查看错误：**
```bash
# 查看 Job 日志
kubectl -n dev logs -l component=migration --tail=100

# 查看 ArgoCD Application 状态
kubectl -n argocd get application youngth-guard-backend -o yaml
```

**修复步骤：**
1. 检查迁移 SQL 语法
2. 修复 Git 仓库中的迁移文件
3. 手动触发 ArgoCD Sync，或等待自动同步
4. 验证迁移成功

### 场景 2：数据库连接失败

```
Init Container (wait-for-db) 失败
  ↓
Job 一直 Pending
  ↓
ArgoCD 等待超时（默认 5 分钟）
  ↓
Sync 失败
```

**原因：**
- Secret 不存在或错误
- 数据库服务不可用
- 网络策略阻止连接

**修复步骤：**
```bash
# 1. 检查 Secret
kubectl -n dev get secret postgres-youngth-guard-dev

# 2. 测试连接
kubectl run -it --rm psql-test \
  --image=postgres:16-alpine \
  --namespace=dev \
  --restart=Never \
  -- sh -c 'export $(kubectl get secret postgres-youngth-guard-dev -o jsonpath="{.data.DATABASE_URL}" | base64 -d) && pg_isready -d $DATABASE_URL'

# 3. 检查数据库 Pod
kubectl -n infra get pods -l app=postgres
```

### 场景 3：迁移文件缺失

```
Flyway 启动
  ↓
未找到迁移文件（/flyway/sql 为空）
  ↓
Flyway 报错或跳过
  ↓
Job 成功（但实际没有执行迁移）
```

**预防：**
```yaml
# 在 Job 中添加验证
command:
  - /bin/sh
  - -c
  - |
    # 检查迁移文件
    if [ ! "$(ls -A /flyway/sql)" ]; then
      echo "ERROR: No migration files found in /flyway/sql"
      exit 1
    fi

    # 执行迁移
    flyway migrate
```

### 场景 4：迁移部分成功

```
V1 迁移成功
V2 迁移成功
V3 迁移失败（SQL 错误）
  ↓
Flyway 记录 V3 失败
  ↓
Job 失败
```

**状态：**
- V1, V2 已应用到数据库
- V3 标记为失败，未应用

**修复步骤：**
```bash
# 1. 连接数据库查看状态
kubectl -n infra exec -it postgres-0 -- psql -U postgres -d youngth_guard_dev

# 2. 检查 Flyway 历史
SELECT * FROM flyway_schema_history ORDER BY installed_rank;

# 3. 如果需要手动修复
# 修复数据库状态，然后标记迁移为成功
UPDATE flyway_schema_history SET success = true WHERE version = '3';

# 或者删除失败记录，修复 SQL 后重新运行
DELETE FROM flyway_schema_history WHERE version = '3';
```

---

## ✅ 验证迁移成功

### 检查清单

```bash
# 1. 查看 Job 状态
kubectl -n dev get job -l component=migration

# 预期输出：
# NAME           COMPLETIONS   DURATION   AGE
# db-migration   1/1           15s        2m

# 2. 查看 Job 日志
kubectl -n dev logs -l component=migration --tail=50

# 预期包含：
# ✅ Migration completed successfully

# 3. 检查 Flyway 历史
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT version, description, installed_on, success FROM flyway_schema_history ORDER BY installed_rank;"

# 4. 验证应用部署
kubectl -n dev get pods -l app=youngth-guard-backend

# 5. 检查应用日志（应该能连接数据库）
kubectl -n dev logs -l app=youngth-guard-backend --tail=20
```

---

## 🔄 完整集成示例

### 目录结构

```
apps/youngth-guard/overlays/dev/
├── kustomization.yaml
├── deployment.yaml
├── service.yaml
├── db-migration-job.yaml        # PreSync Hook
└── db-migrations-configmap.yaml # 迁移文件（或使用镜像）
```

### kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: dev

resources:
  - ../../base
  - db-migration-job.yaml
  - db-migrations-configmap.yaml

images:
  - name: ghcr.io/brunogaosz/youngth-guard-backend
    newName: ghcr.io/brunogaosz/youngth-guard-backend
    newTag: "dev-abc1234"
```

### ArgoCD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: youngth-guard-backend
  namespace: argocd
spec:
  project: default

  source:
    repoURL: https://github.com/BrunoGaoSZ/ljwx-deploy.git
    targetRevision: main
    path: apps/youngth-guard/overlays/dev

  destination:
    server: https://kubernetes.default.svc
    namespace: dev

  syncPolicy:
    automated:
      prune: true
      selfHeal: true

    syncOptions:
      - CreateNamespace=true

    # 重要：失败时不继续
    retry:
      limit: 2
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 1m
```

---

## 🐛 调试技巧

### 手动运行迁移 Job

```bash
# 1. 从 PreSync Job 创建手动 Job
kubectl -n dev get job db-migration -o yaml | \
  sed 's/argocd.argoproj.io\/hook: PreSync//' | \
  sed 's/name: db-migration/name: db-migration-manual/' | \
  kubectl apply -f -

# 2. 查看日志
kubectl -n dev logs -f job/db-migration-manual

# 3. 清理
kubectl -n dev delete job db-migration-manual
```

### 跳过迁移（紧急情况）

```yaml
# 临时移除 PreSync Hook
metadata:
  annotations:
    # argocd.argoproj.io/hook: PreSync  # 注释掉
    argocd.argoproj.io/hook: Skip
```

⚠️ **危险操作！** 仅在紧急情况使用，之后必须手动执行迁移。

### 查看 ArgoCD 事件

```bash
# 查看 Application 事件
kubectl -n argocd describe application youngth-guard-backend

# 查看最近的 Sync
kubectl -n argocd get application youngth-guard-backend -o jsonpath='{.status.operationState}'
```

---

## 📚 最佳实践

1. **迁移文件版本化**
   - 迁移文件提交到 Git
   - 和代码一起审查

2. **测试迁移**
   - 在本地数据库测试
   - 在测试环境验证
   - 使用 Flyway validate 检查

3. **监控迁移**
   - 设置告警（迁移失败）
   - 记录迁移时间
   - 定期审查 flyway_schema_history

4. **备份数据**
   - 迁移前自动备份（通过 PreSync 触发）
   - 保留最近 7 天备份

5. **文档化**
   - 每个迁移都有清晰注释
   - 记录回滚步骤
   - 说明业务影响

---

## 📖 相关文档

- `docs/flyway-guide/README.md` - Flyway 规范和示例
- `docs/db-isolation-spec.md` - 数据库隔离规范
- `docs/architecture-overview.md` - 平台架构说明
- `infra/postgres/README.md` - Postgres 部署文档
- ArgoCD Hooks 官方文档：https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/
