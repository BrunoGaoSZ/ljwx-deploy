# 迁移执行 Checklist

## 📋 概述

本文档提供两个 Checklist，帮助团队快速、安全地接入 infra Postgres：

- **Checklist A：新项目接入 infra Postgres**
- **Checklist B：现有项目迁移到 infra Postgres**

**核心原则：**
- ✅ 每个步骤都有验证标准
- ✅ 所有操作都可回滚
- ✅ 先在测试环境验证，再部署生产
- ✅ 保留完整的操作日志

---

## 📦 Checklist A：新项目接入 infra Postgres

**适用场景：** 全新项目，从零开始配置数据库。

### 阶段 1：前置准备

#### ☐ 1.1 确定项目信息

```bash
# 填写以下信息：
PROJECT_NAME="youngth-guard"      # 项目名（下划线分隔）
ENV="dev"                          # 环境：dev / staging / prod
APP_NAMESPACE="dev"                # 应用部署的 namespace
```

**验证：**
- [ ] 项目名符合命名规范（小写字母、数字、下划线）
- [ ] 环境名称正确（dev / staging / prod）
- [ ] Namespace 已存在

```bash
kubectl get namespace $APP_NAMESPACE
# 如果不存在，创建：
kubectl create namespace $APP_NAMESPACE
```

#### ☐ 1.2 确认 infra Postgres 已部署

```bash
# 检查 Postgres StatefulSet
kubectl -n infra get statefulset postgres

# 预期输出：
# NAME       READY   AGE
# postgres   1/1     Xd

# 检查 Postgres 服务
kubectl -n infra get svc postgres-lb

# 预期输出：
# NAME          TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)    AGE
# postgres-lb   ClusterIP   10.x.x.x      <none>        5432/TCP   Xd

# 测试连接
kubectl -n infra exec postgres-0 -- pg_isready
# 预期输出：/var/run/postgresql:5432 - accepting connections
```

**验证：**
- [ ] StatefulSet READY 状态为 1/1
- [ ] Service 存在且 CLUSTER-IP 已分配
- [ ] pg_isready 返回 "accepting connections"

#### ☐ 1.3 确认 provisioning 脚本就绪

```bash
# 检查 provisioning 资源
kubectl -n infra get configmap create-db-script
kubectl -n infra get serviceaccount postgres-provisioner
kubectl -n infra get clusterrole postgres-provisioner
kubectl -n infra get clusterrolebinding postgres-provisioner

# 预期：所有资源都存在
```

**验证：**
- [ ] ConfigMap `create-db-script` 存在
- [ ] RBAC 资源（ServiceAccount/ClusterRole/ClusterRoleBinding）存在

---

### 阶段 2：创建数据库和用户

#### ☐ 2.1 执行 provisioning Job

```bash
# 创建 Job（替换环境变量）
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: provision-${PROJECT_NAME}-${ENV}
  namespace: infra
spec:
  backoffLimit: 1
  template:
    metadata:
      labels:
        app: postgres-provisioning
    spec:
      serviceAccountName: postgres-provisioner
      restartPolicy: Never
      containers:
        - name: provisioner
          image: postgres:16-alpine
          command:
            - /bin/sh
            - -c
            - |
              # Install kubectl
              apk add --no-cache curl
              curl -LO "https://dl.k8s.io/release/\$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
              chmod +x kubectl
              mv kubectl /usr/local/bin/

              # Run provisioning script
              /bin/bash /scripts/create-db-user.sh
          env:
            - name: PROJECT_NAME
              value: "${PROJECT_NAME}"
            - name: ENV
              value: "${ENV}"
            - name: APP_NAMESPACE
              value: "${APP_NAMESPACE}"
            - name: POSTGRES_ADMIN_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-admin
                  key: POSTGRES_USER
            - name: POSTGRES_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-admin
                  key: POSTGRES_PASSWORD
            - name: POSTGRES_HOST
              value: "postgres-lb.infra.svc.cluster.local"
            - name: POSTGRES_PORT
              value: "5432"
          volumeMounts:
            - name: script
              mountPath: /scripts
      volumes:
        - name: script
          configMap:
            name: create-db-script
EOF

# 等待 Job 完成
kubectl -n infra wait --for=condition=complete --timeout=120s job/provision-${PROJECT_NAME}-${ENV}

# 查看日志
kubectl -n infra logs job/provision-${PROJECT_NAME}-${ENV}
```

**预期日志输出：**
```
============================================
Provisioning database for youngth-guard (dev)
============================================
✅ Database youngth_guard_dev created
✅ User youngth_guard_dev_user created
✅ Privileges granted
✅ Secret postgres-youngth-guard-dev created in namespace dev
✅ Provisioning completed successfully
```

**验证：**
- [ ] Job 状态为 Completed (1/1)
- [ ] 日志中显示 "✅ Provisioning completed successfully"
- [ ] 没有错误信息

#### ☐ 2.2 验证数据库创建

```bash
# 连接 Postgres 验证数据库
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -c "\l" | grep ${PROJECT_NAME}_${ENV}

# 预期输出：
# youngth_guard_dev | youngth_guard_dev_user | UTF8 | ...

# 验证用户
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -c "\du" | grep ${PROJECT_NAME}_${ENV}_user

# 预期输出：
# youngth_guard_dev_user | ...

# 测试用户连接
DB_PASSWORD=$(kubectl -n $APP_NAMESPACE get secret postgres-${PROJECT_NAME}-${ENV} -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)

kubectl -n infra exec postgres-0 -- \
  psql -U ${PROJECT_NAME}_${ENV}_user \
       -d ${PROJECT_NAME}_${ENV} \
       -c "SELECT current_database(), current_user;"

# 预期输出：
#  current_database    |      current_user
# ---------------------+------------------------
#  youngth_guard_dev   | youngth_guard_dev_user
```

**验证：**
- [ ] 数据库已创建且 Owner 正确
- [ ] 用户已创建
- [ ] 用户可以连接到数据库

#### ☐ 2.3 验证 Secret 创建

```bash
# 检查 Secret 是否存在
kubectl -n $APP_NAMESPACE get secret postgres-${PROJECT_NAME}-${ENV}

# 查看 Secret 内容
kubectl -n $APP_NAMESPACE get secret postgres-${PROJECT_NAME}-${ENV} -o yaml

# 验证 Secret 包含必要的 key
kubectl -n $APP_NAMESPACE get secret postgres-${PROJECT_NAME}-${ENV} \
  -o jsonpath='{.data}' | jq 'keys'

# 预期输出：
# [
#   "DATABASE_URL",
#   "POSTGRES_DB",
#   "POSTGRES_HOST",
#   "POSTGRES_PASSWORD",
#   "POSTGRES_PORT",
#   "POSTGRES_USER"
# ]

# 测试 DATABASE_URL 格式
kubectl -n $APP_NAMESPACE get secret postgres-${PROJECT_NAME}-${ENV} \
  -o jsonpath='{.data.DATABASE_URL}' | base64 -d
# 预期输出：postgresql://youngth_guard_dev_user:***@postgres-lb.infra.svc.cluster.local:5432/youngth_guard_dev
```

**验证：**
- [ ] Secret 存在于应用 namespace
- [ ] Secret 包含所有必要的 key（6 个）
- [ ] DATABASE_URL 格式正确

---

### 阶段 3：配置应用连接数据库

#### ☐ 3.1 更新应用 Deployment

```bash
# 编辑应用 Deployment
cd ljwx-deploy/apps/${PROJECT_NAME}/overlays/${ENV}

# 示例：apps/youngth-guard/overlays/dev/deployment.yaml
```

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: youngth-guard-backend
spec:
  template:
    spec:
      containers:
        - name: backend
          image: ghcr.io/brunogaosz/youngth-guard-backend:latest
          env:
            # 从 Secret 读取数据库配置
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: DATABASE_URL
            # 或者单独配置
            - name: POSTGRES_HOST
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_HOST
            - name: POSTGRES_PORT
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_PORT
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_DB
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_PASSWORD
```

**验证：**
- [ ] Deployment 已配置数据库环境变量
- [ ] Secret 引用正确（name 和 key）
- [ ] 应用代码支持这些环境变量

#### ☐ 3.2 提交配置到 GitOps 仓库

```bash
# 添加并提交
git add apps/${PROJECT_NAME}/overlays/${ENV}/deployment.yaml
git commit -m "feat: configure ${PROJECT_NAME}-${ENV} to use infra Postgres"
git push origin main

# ArgoCD 会自动检测并部署
```

**验证：**
- [ ] 代码已推送到 main 分支
- [ ] ArgoCD Application 显示 "Syncing"

---

### 阶段 4：配置 Flyway 数据库迁移

#### ☐ 4.1 创建迁移文件

```bash
# 在应用代码仓库创建迁移目录
cd /path/to/${PROJECT_NAME}
mkdir -p backend/migrations

# 创建初始 Schema 迁移
cat > backend/migrations/V1__initial_schema.sql <<'EOF'
-- ============================================
-- Migration: V1__initial_schema
-- Description: 初始化数据库 Schema
-- Author: YourName
-- Date: $(date +%Y-%m-%d)
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

COMMENT ON TABLE users IS '用户表';
EOF

# 提交迁移文件
git add backend/migrations/V1__initial_schema.sql
git commit -m "feat: add initial database schema migration"
git push origin main
```

**验证：**
- [ ] 迁移文件命名符合 Flyway 规范（V{版本}__{描述}.sql）
- [ ] SQL 语句使用 IF NOT EXISTS（幂等）
- [ ] 迁移文件已提交到代码仓库

#### ☐ 4.2 配置 ArgoCD PreSync Hook

```bash
# 在 GitOps 仓库创建 PreSync Job
cd ljwx-deploy/apps/${PROJECT_NAME}/overlays/${ENV}

# 创建 db-migration-job.yaml
cat > db-migration-job.yaml <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
    argocd.argoproj.io/sync-wave: "-1"
  labels:
    app: ${PROJECT_NAME}-backend
    component: migration
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        component: migration
    spec:
      restartPolicy: Never
      initContainers:
        - name: wait-for-db
          image: postgres:16-alpine
          command:
            - /bin/sh
            - -c
            - |
              echo "Waiting for database..."
              until pg_isready -h \$POSTGRES_HOST -p \$POSTGRES_PORT -U \$POSTGRES_USER; do
                sleep 2
              done
              echo "Database ready!"
          env:
            - name: POSTGRES_HOST
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_HOST
            - name: POSTGRES_PORT
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_PORT
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_USER
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_PASSWORD
      containers:
        - name: flyway
          image: flyway/flyway:10-alpine
          command:
            - /bin/sh
            - -c
            - |
              set -e
              echo "Running Flyway migrations..."
              flyway -connectRetries=3 migrate
              echo "Migration completed!"
              flyway info
          env:
            - name: FLYWAY_URL
              value: "jdbc:postgresql://\$(POSTGRES_HOST):\$(POSTGRES_PORT)/\$(POSTGRES_DB)"
            - name: FLYWAY_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_USER
            - name: FLYWAY_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_PASSWORD
            - name: POSTGRES_HOST
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_HOST
            - name: POSTGRES_PORT
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_PORT
            - name: POSTGRES_DB
              valueFrom:
                secretKeyRef:
                  name: postgres-${PROJECT_NAME}-${ENV}
                  key: POSTGRES_DB
            - name: FLYWAY_BASELINE_ON_MIGRATE
              value: "true"
            - name: FLYWAY_BASELINE_VERSION
              value: "0"
          volumeMounts:
            - name: migrations
              mountPath: /flyway/sql
              readOnly: true
      volumes:
        - name: migrations
          configMap:
            name: db-migrations
EOF

# 将迁移文件打包为 ConfigMap（临时方案，生产建议打包到镜像）
kubectl -n $APP_NAMESPACE create configmap db-migrations \
  --from-file=/path/to/${PROJECT_NAME}/backend/migrations/ \
  --dry-run=client -o yaml > db-migrations-configmap.yaml

# 添加到 kustomization.yaml
cat >> kustomization.yaml <<EOF

resources:
  - db-migration-job.yaml
  - db-migrations-configmap.yaml
EOF

# 提交
git add db-migration-job.yaml db-migrations-configmap.yaml kustomization.yaml
git commit -m "feat: add database migration PreSync hook for ${PROJECT_NAME}-${ENV}"
git push origin main
```

**验证：**
- [ ] PreSync Job 配置正确（annotations）
- [ ] Secret 引用正确
- [ ] 迁移文件已打包为 ConfigMap
- [ ] kustomization.yaml 已更新

---

### 阶段 5：部署和验证

#### ☐ 5.1 触发 ArgoCD Sync

```bash
# 方法 1：等待自动 Sync（默认 3 分钟）

# 方法 2：手动触发 Sync
argocd app sync ${PROJECT_NAME}-backend

# 或使用 kubectl
kubectl -n argocd patch application ${PROJECT_NAME}-backend \
  --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{}}}'

# 监控 Sync 进度
kubectl -n argocd get application ${PROJECT_NAME}-backend -w
```

**验证：**
- [ ] Application 状态变为 "Syncing"
- [ ] PreSync Job 开始执行

#### ☐ 5.2 验证迁移执行

```bash
# 查看 PreSync Job 状态
kubectl -n $APP_NAMESPACE get job -l component=migration

# 预期输出：
# NAME           COMPLETIONS   DURATION   AGE
# db-migration   1/1           15s        1m

# 查看 Job 日志
kubectl -n $APP_NAMESPACE logs -l component=migration --tail=100

# 预期包含：
# ✅ Migration completed successfully
# Flyway info output...

# 验证 Flyway 历史表
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} -c \
  "SELECT version, description, installed_on, success FROM flyway_schema_history ORDER BY installed_rank;"

# 预期输出：
#  version |     description     |     installed_on        | success
# ---------+---------------------+-------------------------+---------
#  1       | initial schema      | 2025-01-18 10:00:00     | t
```

**验证：**
- [ ] Job 状态为 Completed (1/1)
- [ ] 日志显示迁移成功
- [ ] flyway_schema_history 表包含 V1 记录且 success = true

#### ☐ 5.3 验证应用部署

```bash
# 查看 Pod 状态
kubectl -n $APP_NAMESPACE get pods -l app=${PROJECT_NAME}-backend

# 预期输出：
# NAME                                   READY   STATUS    RESTARTS   AGE
# youngth-guard-backend-xxxxx-yyyyy      1/1     Running   0          2m

# 查看应用日志
kubectl -n $APP_NAMESPACE logs -l app=${PROJECT_NAME}-backend --tail=50

# 预期：无数据库连接错误，应用正常启动

# 测试健康检查
kubectl -n $APP_NAMESPACE get pods -l app=${PROJECT_NAME}-backend \
  -o jsonpath='{.items[0].metadata.name}' | \
  xargs -I {} kubectl -n $APP_NAMESPACE exec {} -- curl -s http://localhost:8000/health

# 或通过 Service
kubectl -n $APP_NAMESPACE run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
  curl http://${PROJECT_NAME}-backend:8000/health

# 预期输出：{"status": "ok"}
```

**验证：**
- [ ] Pod 状态为 Running，Ready 1/1
- [ ] 应用日志无数据库连接错误
- [ ] 健康检查返回正常

#### ☐ 5.4 验证数据库连接

```bash
# 从应用 Pod 内部测试数据库连接
kubectl -n $APP_NAMESPACE exec -it \
  $(kubectl -n $APP_NAMESPACE get pods -l app=${PROJECT_NAME}-backend -o jsonpath='{.items[0].metadata.name}') \
  -- /bin/sh

# 在 Pod 内执行：
env | grep POSTGRES
# 应该显示所有数据库环境变量

# 测试连接（如果 Pod 内有 psql）
psql $DATABASE_URL -c "SELECT current_database(), current_user;"

# 或使用应用自带的 DB 健康检查
exit

# 查看数据库表
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} -c "\dt"

# 预期：显示应用创建的表（来自迁移）
```

**验证：**
- [ ] 环境变量正确注入
- [ ] 应用可以连接数据库
- [ ] 数据库表已创建

---

### 阶段 6：清理和文档

#### ☐ 6.1 清理临时资源

```bash
# 删除 provisioning Job（保留日志可选）
kubectl -n infra delete job provision-${PROJECT_NAME}-${ENV}

# 清理成功的迁移 Job（保留日志可选）
# kubectl -n $APP_NAMESPACE delete job db-migration
```

**验证：**
- [ ] 临时 Job 已清理（或根据团队策略保留）

#### ☐ 6.2 更新文档

```markdown
# 在项目 README.md 添加数据库信息

## 数据库配置

- **数据库类型：** PostgreSQL 16
- **部署位置：** infra namespace (共享 Postgres)
- **数据库名：** youngth_guard_dev
- **Secret：** postgres-youngth-guard-dev (dev namespace)
- **连接地址：** postgres-lb.infra.svc.cluster.local:5432
- **迁移工具：** Flyway
- **迁移文件：** backend/migrations/

## 数据库操作

### 连接数据库
\`\`\`bash
kubectl -n infra exec -it postgres-0 -- psql -U postgres -d youngth_guard_dev
\`\`\`

### 查看迁移历史
\`\`\`bash
kubectl -n infra exec postgres-0 -- \\
  psql -U postgres -d youngth_guard_dev -c \\
  "SELECT * FROM flyway_schema_history ORDER BY installed_rank;"
\`\`\`

### 添加新迁移
1. 在 `backend/migrations/` 创建 `V{N+1}__description.sql`
2. 遵循 Flyway 规范（参考 `docs/flyway-guide/README.md`）
3. 提交到 Git
4. ArgoCD 自动执行迁移
```

**验证：**
- [ ] 项目文档已更新
- [ ] 包含数据库连接和迁移操作说明

---

### ✅ Checklist A 完成

**最终验证：**
- [ ] 数据库已创建并可访问
- [ ] Secret 存在且包含正确信息
- [ ] 应用可以连接数据库
- [ ] Flyway 迁移成功执行
- [ ] 应用正常运行
- [ ] 文档已更新

**常见问题排查：** 参见文档末尾 FAQ 部分

---

## 🔄 Checklist B：现有项目迁移到 infra Postgres

**适用场景：** 现有项目使用独立 Postgres（单独 StatefulSet 或云数据库），需要迁移到 infra 共享 Postgres。

### 阶段 1：现状评估

#### ☐ 1.1 评估现有数据库

```bash
# 确定现有数据库位置
PROJECT_NAME="youngth-guard"
OLD_NAMESPACE="dev"  # 假设现有数据库在 dev namespace

# 检查现有 Postgres 部署
kubectl -n $OLD_NAMESPACE get statefulset -l app=postgres
kubectl -n $OLD_NAMESPACE get deployment -l app=postgres

# 记录当前配置
OLD_DB_HOST=$(kubectl -n $OLD_NAMESPACE get secret ${PROJECT_NAME}-db -o jsonpath='{.data.POSTGRES_HOST}' | base64 -d)
OLD_DB_PORT=$(kubectl -n $OLD_NAMESPACE get secret ${PROJECT_NAME}-db -o jsonpath='{.data.POSTGRES_PORT}' | base64 -d)
OLD_DB_NAME=$(kubectl -n $OLD_NAMESPACE get secret ${PROJECT_NAME}-db -o jsonpath='{.data.POSTGRES_DB}' | base64 -d)
OLD_DB_USER=$(kubectl -n $OLD_NAMESPACE get secret ${PROJECT_NAME}-db -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)
OLD_DB_PASSWORD=$(kubectl -n $OLD_NAMESPACE get secret ${PROJECT_NAME}-db -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)

echo "Current database:"
echo "  Host: $OLD_DB_HOST"
echo "  Port: $OLD_DB_PORT"
echo "  Database: $OLD_DB_NAME"
echo "  User: $OLD_DB_USER"
```

**验证：**
- [ ] 记录了现有数据库的所有连接信息
- [ ] 确认现有数据库类型（PostgreSQL 版本）
- [ ] 确认数据量大小

#### ☐ 1.2 评估数据量和停机时间

```bash
# 连接现有数据库查看数据量
kubectl -n $OLD_NAMESPACE exec -it \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U $OLD_DB_USER -d $OLD_DB_NAME

# 在 psql 中执行：
\l+  -- 查看数据库大小
\dt+ -- 查看表大小
SELECT count(*) FROM users;  -- 查看关键表行数

# 评估备份时间
\q

# 测试 pg_dump 速度
time kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- pg_dump -U $OLD_DB_USER -d $OLD_DB_NAME -Fc -f /tmp/test_backup.dump

# 根据速度评估停机时间窗口
```

**记录：**
- 数据库大小：______ MB
- 表数量：______ 个
- 最大表行数：______ 行
- 预估备份时间：______ 分钟
- 预估恢复时间：______ 分钟
- 建议停机窗口：______ 分钟

**验证：**
- [ ] 了解数据量
- [ ] 评估了迁移时间
- [ ] 确定停机窗口（或零停机方案）

#### ☐ 1.3 制定迁移计划

**选择迁移策略：**

**策略 A：停机迁移**（数据量小，< 1GB）
- 停止应用 → 备份 → 恢复 → 切换配置 → 启动应用
- 停机时间：10-30 分钟

**策略 B：灰度迁移**（数据量大，> 1GB 或不能停机）
- 双写（新旧数据库） → 验证 → 切换读 → 停止旧库
- 停机时间：< 5 分钟（切换瞬间）

**本 Checklist 采用策略 A（停机迁移），策略 B 请联系 DBA。**

**验证：**
- [ ] 选择了合适的迁移策略
- [ ] 获得了停机窗口批准
- [ ] 通知了相关团队

---

### 阶段 2：备份现有数据库

#### ☐ 2.1 创建完整备份

```bash
# 创建备份目录
kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- mkdir -p /tmp/backup

# 执行 pg_dump
BACKUP_FILE="${PROJECT_NAME}_${OLD_DB_NAME}_$(date +%Y%m%d_%H%M%S).dump"

kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- pg_dump -U $OLD_DB_USER -d $OLD_DB_NAME -Fc -f /tmp/backup/$BACKUP_FILE

# 验证备份文件
kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- ls -lh /tmp/backup/$BACKUP_FILE

# 复制备份到本地（可选，推荐）
kubectl -n $OLD_NAMESPACE cp \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}'):/tmp/backup/$BACKUP_FILE \
  ./$BACKUP_FILE

echo "Backup saved to: ./$BACKUP_FILE"
```

**验证：**
- [ ] 备份文件已创建
- [ ] 备份文件大小合理（不是 0 字节）
- [ ] 备份文件已复制到本地（安全起见）

#### ☐ 2.2 验证备份完整性

```bash
# 测试恢复到临时数据库（可选但推荐）
kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U postgres -c "CREATE DATABASE test_restore_db;"

kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- pg_restore -U postgres -d test_restore_db -Fc /tmp/backup/$BACKUP_FILE

# 验证表数量
kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U postgres -d test_restore_db -c "\dt"

# 验证数据行数
kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U postgres -d test_restore_db -c "SELECT count(*) FROM users;"

# 清理测试数据库
kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U postgres -c "DROP DATABASE test_restore_db;"
```

**验证：**
- [ ] 备份可以成功恢复
- [ ] 表数量与原库一致
- [ ] 关键表行数与原库一致

---

### 阶段 3：在 infra Postgres 创建新数据库

#### ☐ 3.1 执行 provisioning（参考 Checklist A 步骤 2.1）

```bash
# 使用 Checklist A 的步骤 2.1 创建数据库
ENV="dev"  # 或 staging / prod

# 执行 provisioning Job
# ... (参考 Checklist A)
```

**验证：**
- [ ] 新数据库已创建（${PROJECT_NAME}_${ENV}）
- [ ] 新用户已创建
- [ ] Secret 已创建

---

### 阶段 4：迁移数据

#### ☐ 4.1 停止应用（防止数据写入）

```bash
# 缩容应用到 0
kubectl -n $OLD_NAMESPACE scale deployment ${PROJECT_NAME}-backend --replicas=0

# 等待 Pod 终止
kubectl -n $OLD_NAMESPACE wait --for=delete pod -l app=${PROJECT_NAME}-backend --timeout=60s

# 验证无 Pod 运行
kubectl -n $OLD_NAMESPACE get pods -l app=${PROJECT_NAME}-backend
# 预期：No resources found
```

**验证：**
- [ ] 应用已停止
- [ ] 无 Pod 运行
- [ ] 记录停机开始时间：________

#### ☐ 4.2 最终备份（可选，如果 2.1 备份较早）

```bash
# 如果 2.1 备份是几小时前做的，重新备份
FINAL_BACKUP_FILE="${PROJECT_NAME}_${OLD_DB_NAME}_final_$(date +%Y%m%d_%H%M%S).dump"

kubectl -n $OLD_NAMESPACE exec \
  $(kubectl -n $OLD_NAMESPACE get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- pg_dump -U $OLD_DB_USER -d $OLD_DB_NAME -Fc -f /tmp/backup/$FINAL_BACKUP_FILE

# 使用这个备份文件进行恢复
BACKUP_FILE=$FINAL_BACKUP_FILE
```

#### ☐ 4.3 上传备份到 infra Postgres

```bash
# 将备份文件复制到 infra Postgres Pod
kubectl -n infra cp \
  ./$BACKUP_FILE \
  postgres-0:/tmp/$BACKUP_FILE

# 验证文件已上传
kubectl -n infra exec postgres-0 -- ls -lh /tmp/$BACKUP_FILE
```

**验证：**
- [ ] 备份文件已上传到 infra Postgres
- [ ] 文件大小正确

#### ☐ 4.4 恢复数据到新数据库

```bash
# 恢复数据
kubectl -n infra exec postgres-0 -- \
  pg_restore -U postgres -d ${PROJECT_NAME}_${ENV} \
  --no-owner --no-acl \
  -Fc /tmp/$BACKUP_FILE

# 如果报错 "already exists"，可以忽略（幂等）
# 或使用 --clean 选项（先删除再创建）

# 验证恢复后的表
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} -c "\dt"

# 验证数据行数
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} -c "SELECT count(*) FROM users;"

# 对比原库行数（应该一致）
```

**验证：**
- [ ] 数据恢复成功
- [ ] 表数量与原库一致
- [ ] 关键表行数与原库一致

#### ☐ 4.5 修复权限

```bash
# pg_restore 使用 --no-owner，需要重新授权
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} <<EOF
-- 授予用户对所有表的权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${PROJECT_NAME}_${ENV}_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${PROJECT_NAME}_${ENV}_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO ${PROJECT_NAME}_${ENV}_user;

-- 设置默认权限（新创建的对象）
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${PROJECT_NAME}_${ENV}_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${PROJECT_NAME}_${ENV}_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO ${PROJECT_NAME}_${ENV}_user;
EOF

# 验证权限
kubectl -n infra exec postgres-0 -- \
  psql -U ${PROJECT_NAME}_${ENV}_user -d ${PROJECT_NAME}_${ENV} -c "SELECT * FROM users LIMIT 1;"
# 应该可以查询成功
```

**验证：**
- [ ] 用户可以查询表
- [ ] 用户可以插入/更新/删除（如果需要）

---

### 阶段 5：切换应用配置

#### ☐ 5.1 更新 Deployment 使用新 Secret

```bash
# 编辑 Deployment
cd ljwx-deploy/apps/${PROJECT_NAME}/overlays/${ENV}

# 更新 deployment.yaml，将 Secret 引用改为新的
# 原来：secretKeyRef.name: youngth-guard-db
# 改为：secretKeyRef.name: postgres-youngth-guard-dev

# 示例 patch
kubectl -n $OLD_NAMESPACE patch deployment ${PROJECT_NAME}-backend --type json -p='[
  {
    "op": "replace",
    "path": "/spec/template/spec/containers/0/env",
    "value": [
      {
        "name": "DATABASE_URL",
        "valueFrom": {
          "secretKeyRef": {
            "name": "postgres-'${PROJECT_NAME}'-'${ENV}'",
            "key": "DATABASE_URL"
          }
        }
      }
    ]
  }
]'

# 或通过 GitOps 更新（推荐）
# 编辑 deployment.yaml，提交到 Git
```

**验证：**
- [ ] Deployment 配置已更新
- [ ] Secret 引用指向新 Secret

#### ☐ 5.2 启动应用

```bash
# 如果通过 GitOps 更新，触发 ArgoCD Sync
argocd app sync ${PROJECT_NAME}-backend

# 或直接扩容（如果手动 patch）
kubectl -n $OLD_NAMESPACE scale deployment ${PROJECT_NAME}-backend --replicas=3

# 等待 Pod 启动
kubectl -n $OLD_NAMESPACE wait --for=condition=ready pod -l app=${PROJECT_NAME}-backend --timeout=120s

# 查看 Pod 状态
kubectl -n $OLD_NAMESPACE get pods -l app=${PROJECT_NAME}-backend
```

**验证：**
- [ ] Pod 状态为 Running
- [ ] Pod Ready 1/1

#### ☐ 5.3 验证应用连接新数据库

```bash
# 查看应用日志
kubectl -n $OLD_NAMESPACE logs -l app=${PROJECT_NAME}-backend --tail=100

# 预期：
# - 显示连接到 postgres-lb.infra.svc.cluster.local
# - 无数据库连接错误

# 测试健康检查
kubectl -n $OLD_NAMESPACE run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
  curl http://${PROJECT_NAME}-backend:8000/health

# 预期输出：{"status": "ok"}

# 测试业务功能（读写数据）
# 例如：登录、创建用户、查询数据等
```

**验证：**
- [ ] 应用日志显示连接到新数据库
- [ ] 健康检查通过
- [ ] 业务功能正常（读写数据成功）
- [ ] 记录恢复服务时间：________

---

### 阶段 6：配置 Flyway 和 PreSync Hook

#### ☐ 6.1 添加 Flyway baseline

```bash
# 由于数据是直接恢复的（非 Flyway 管理），需要 baseline
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} <<EOF
-- 创建 Flyway 历史表
CREATE TABLE IF NOT EXISTS flyway_schema_history (
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

-- 插入 baseline 记录
INSERT INTO flyway_schema_history (
    installed_rank, version, description, type, script,
    installed_by, installed_on, execution_time, success
) VALUES (
    1, '0', '<< Flyway Baseline >>', 'BASELINE', '<< Flyway Baseline >>',
    'manual', NOW(), 0, true
);
EOF

# 验证
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d ${PROJECT_NAME}_${ENV} -c \
  "SELECT * FROM flyway_schema_history;"
```

**验证：**
- [ ] flyway_schema_history 表已创建
- [ ] Baseline 记录已插入

#### ☐ 6.2 创建迁移文件（参考 Checklist A 步骤 4.1-4.2）

```bash
# 后续新的 Schema 变更使用 Flyway 管理
# 参考 Checklist A 步骤 4.1-4.2
```

---

### 阶段 7：清理旧资源

⚠️ **警告：仅在确认新数据库稳定运行至少 7 天后执行清理！**

#### ☐ 7.1 保留旧数据库（观察期）

```bash
# 在观察期内（建议 7-14 天）：
# - 保留旧 StatefulSet（缩容到 0）
# - 保留旧 PVC（数据备份）
# - 定期检查新数据库运行状况

# 缩容旧 Postgres（不删除）
kubectl -n $OLD_NAMESPACE scale statefulset postgres --replicas=0
```

**验证：**
- [ ] 旧数据库已停止但未删除
- [ ] 数据仍在 PVC 中

#### ☐ 7.2 清理旧资源（观察期后）

```bash
# 7-14 天后，确认新库稳定，执行清理

# 删除旧 StatefulSet
kubectl -n $OLD_NAMESPACE delete statefulset postgres

# 删除旧 Service
kubectl -n $OLD_NAMESPACE delete service postgres

# 删除旧 Secret
kubectl -n $OLD_NAMESPACE delete secret ${PROJECT_NAME}-db

# 可选：删除旧 PVC（数据将永久丢失！）
# kubectl -n $OLD_NAMESPACE delete pvc postgres-data-postgres-0

# 建议：保留 PVC 快照或导出到对象存储后再删除
```

**验证：**
- [ ] 旧 StatefulSet 已删除
- [ ] 旧 Service 已删除
- [ ] 旧 Secret 已删除
- [ ] 根据策略保留或删除 PVC

#### ☐ 7.3 更新文档

```markdown
# 更新项目 README.md 和 CHANGELOG.md

## CHANGELOG.md
### [2025-01-18] Database Migration
- Migrated from standalone Postgres to shared infra Postgres
- Database: youngth_guard_dev
- Migration completed with zero data loss
- Old database decommissioned on 2025-01-25

## README.md
（更新为 Checklist A 的文档模板）
```

**验证：**
- [ ] 文档已更新
- [ ] 记录了迁移日期和关键信息

---

### ✅ Checklist B 完成

**最终验证：**
- [ ] 数据已完整迁移到 infra Postgres
- [ ] 应用连接新数据库正常运行
- [ ] 业务功能验证通过
- [ ] Flyway 配置完成
- [ ] 旧资源已清理（或计划清理）
- [ ] 文档已更新

**迁移总结：**
- 开始时间：________
- 结束时间：________
- 停机时长：________ 分钟
- 数据量：________ MB
- 迁移状态：✅ 成功 / ❌ 失败（如果失败，请记录原因）

---

## ❓ FAQ - 常见问题排查

### Q1: Provisioning Job 失败，提示 "connection refused"

**原因：** Postgres Pod 未就绪或 Service 配置错误。

**排查：**
```bash
# 检查 Postgres Pod
kubectl -n infra get pods -l app=postgres

# 检查 Service
kubectl -n infra get svc postgres-lb

# 测试连接
kubectl -n infra exec postgres-0 -- pg_isready

# 查看 Job 日志
kubectl -n infra logs job/provision-xxx
```

**解决：**
- 等待 Postgres Pod Ready
- 检查 Service ClusterIP 是否分配
- 检查 Secret `postgres-admin` 是否存在且正确

---

### Q2: PreSync Job 失败，提示 "Flyway validation failed"

**原因：** 迁移文件 checksum 变化或顺序错误。

**排查：**
```bash
# 查看 Flyway 日志
kubectl -n dev logs -l component=migration

# 检查 flyway_schema_history
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT * FROM flyway_schema_history WHERE success = false;"
```

**解决：**
```bash
# 方法 1：修复迁移文件后删除失败记录
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "DELETE FROM flyway_schema_history WHERE version = 'X' AND success = false;"

# 方法 2：使用 Flyway repair（如果 checksum 变化）
# 在 Job 中添加：flyway repair
```

---

### Q3: 应用 Pod 启动后立即 CrashLoopBackOff

**原因：** 数据库连接配置错误或数据库未就绪。

**排查：**
```bash
# 查看 Pod 日志
kubectl -n dev logs -l app=youngth-guard-backend --tail=100

# 检查环境变量
kubectl -n dev exec -it <pod-name> -- env | grep POSTGRES

# 检查 Secret
kubectl -n dev get secret postgres-youngth-guard-dev -o yaml

# 测试数据库连接
kubectl -n dev run psql-test --image=postgres:16-alpine --rm -it --restart=Never -- \
  psql $(kubectl -n dev get secret postgres-youngth-guard-dev -o jsonpath='{.data.DATABASE_URL}' | base64 -d)
```

**解决：**
- 检查 Secret 引用是否正确
- 检查 DATABASE_URL 格式
- 检查数据库是否存在且可访问
- 检查应用代码是否支持环境变量

---

### Q4: 数据迁移后发现数据丢失

**原因：** 备份不完整或恢复时跳过了某些对象。

**排查：**
```bash
# 对比表数量
# 原库
kubectl -n old exec <old-pod> -- psql -U user -d db -c "\dt"

# 新库
kubectl -n infra exec postgres-0 -- psql -U postgres -d new_db -c "\dt"

# 对比行数
kubectl -n infra exec postgres-0 -- psql -U postgres -d new_db -c \
  "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

**解决：**
```bash
# 如果发现丢失，立即回滚到旧库
kubectl -n old scale deployment app --replicas=3

# 重新执行备份和恢复
# 使用 pg_dump -Fc（custom format）确保完整性

# 恢复时不使用 --clean，避免删除数据
```

---

### Q5: 如何回滚迁移？

**场景：** 迁移到 infra Postgres 后发现问题，需要回滚到旧库。

**步骤：**
```bash
# 1. 停止应用
kubectl -n dev scale deployment youngth-guard-backend --replicas=0

# 2. 启动旧 Postgres（如果已停止）
kubectl -n old scale statefulset postgres --replicas=1
kubectl -n old wait --for=condition=ready pod/postgres-0

# 3. 恢复应用配置到旧 Secret
kubectl -n dev patch deployment youngth-guard-backend --type json -p='[
  {
    "op": "replace",
    "path": "/spec/template/spec/containers/0/env/0/valueFrom/secretKeyRef/name",
    "value": "youngth-guard-db"
  }
]'

# 4. 启动应用
kubectl -n dev scale deployment youngth-guard-backend --replicas=3

# 5. 验证连接
kubectl -n dev logs -l app=youngth-guard-backend
```

---

### Q6: 如何在不停机的情况下迁移？

**方案：** 双写 + 灰度切换（复杂，建议联系 DBA）

**概要步骤：**
1. 配置应用同时写入旧库和新库
2. 持续同步数据（旧 → 新）
3. 验证数据一致性
4. 切换读流量到新库
5. 停止写入旧库
6. 清理旧库

**注意：** 需要应用代码支持，非本 Checklist 范围。

---

## 📖 相关文档

- `docs/architecture-overview.md` - 平台架构说明
- `docs/db-isolation-spec.md` - 数据库命名和隔离规范
- `docs/flyway-guide/README.md` - Flyway 使用规范
- `docs/argocd-migration/README.md` - PreSync Hook 详解
- `docs/db-migration-playbook.md` - 数据库升级和回滚手册
- `infra/postgres/README.md` - Postgres 部署文档
- `infra/postgres/provisioning/README.md` - 自动化 provisioning 说明

---

## 🎯 总结

**Checklist A（新项目）核心步骤：**
1. Provisioning Job 创建 DB/User/Secret
2. 配置应用连接 infra Postgres
3. 配置 Flyway 迁移
4. 配置 ArgoCD PreSync Hook
5. 部署验证

**Checklist B（现有项目）核心步骤：**
1. 评估现状和数据量
2. 备份现有数据库
3. Provisioning 创建新 DB
4. 恢复数据到新 DB
5. 切换应用配置
6. 配置 Flyway
7. 清理旧资源

**记住：**
- ✅ 每个步骤都要验证
- ✅ 保留完整的备份
- ✅ 先测试环境，再生产环境
- ✅ 所有操作都可回滚
