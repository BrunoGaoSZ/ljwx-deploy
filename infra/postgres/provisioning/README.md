# PostgreSQL 自动创建数据库和用户

## 📋 概述

本目录包含自动化脚本和 Kubernetes Job，用于：
1. 创建项目数据库
2. 创建专用用户
3. 配置最小权限
4. 生成 Kubernetes Secret

**特点：**
- ✅ 幂等性：重复执行安全
- ✅ 自动生成安全密码
- ✅ 遵循命名规范
- ✅ 自动创建 Secret 到目标 namespace
- ✅ 不影响已有项目

---

## 🚀 快速开始

### 前置条件

1. Postgres 已部署在 `infra` namespace
2. `postgres-admin` Secret 已创建
3. 目标 namespace 存在（或脚本会自动创建）

### 步骤 1：部署自动化脚本和 RBAC

```bash
# 部署脚本和权限
kubectl apply -k infra/postgres/provisioning/

# 验证
kubectl -n infra get configmap postgres-provision-script
kubectl -n infra get serviceaccount postgres-provisioner
kubectl get clusterrole postgres-provisioner
```

---

## 📝 使用方法

### 方法 1：使用 Job（推荐）

#### 示例：为 youngth-guard 项目创建 dev 环境数据库

```bash
# 创建 Job（基于模板）
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-provision-youngth-guard-dev
  namespace: infra
  labels:
    app: postgres
    component: provisioning
    project: youngth-guard
    env: dev
spec:
  ttlSecondsAfterFinished: 86400
  backoffLimit: 3
  template:
    metadata:
      labels:
        app: postgres
        component: provisioning
    spec:
      restartPolicy: Never
      serviceAccountName: postgres-provisioner
      containers:
        - name: provision
          image: postgres:16-alpine
          command:
            - /bin/bash
            - /scripts/create-db-user.sh
          env:
            # 项目配置
            - name: PROJECT_NAME
              value: "youngth-guard"
            - name: ENV
              value: "dev"
            - name: TARGET_NAMESPACE
              value: "dev"

            # PostgreSQL 连接
            - name: PGHOST
              value: postgres-lb.infra.svc.cluster.local
            - name: PGPORT
              value: "5432"
            - name: PGUSER
              valueFrom:
                secretKeyRef:
                  name: postgres-admin
                  key: POSTGRES_USER
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-admin
                  key: POSTGRES_PASSWORD
          volumeMounts:
            - name: scripts
              mountPath: /scripts
              readOnly: true
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
      volumes:
        - name: scripts
          configMap:
            name: postgres-provision-script
            defaultMode: 0755
EOF

# 查看 Job 进度
kubectl -n infra logs -f job/postgres-provision-youngth-guard-dev

# 等待完成
kubectl -n infra wait --for=condition=complete job/postgres-provision-youngth-guard-dev --timeout=300s
```

#### 验证结果

```bash
# 1. 检查数据库
kubectl -n infra exec postgres-0 -- psql -U postgres -c "\l youngth_guard_dev"

# 2. 检查用户
kubectl -n infra exec postgres-0 -- psql -U postgres -c "\du youngth_guard_dev_user"

# 3. 检查 Secret
kubectl -n dev get secret postgres-youngth-guard-dev

# 4. 查看 Secret 内容
kubectl -n dev get secret postgres-youngth-guard-dev -o yaml

# 5. 测试连接
kubectl -n dev run psql-test --rm -it --image=postgres:16-alpine --restart=Never -- \
  sh -c 'export $(kubectl get secret postgres-youngth-guard-dev -o jsonpath="{.data.DATABASE_URL}" | base64 -d) && psql $DATABASE_URL -c "SELECT current_database(), current_user;"'
```

---

### 方法 2：手动运行脚本（调试用）

```bash
# 进入 Postgres Pod
kubectl -n infra exec -it postgres-0 -- bash

# 下载脚本
kubectl -n infra get configmap postgres-provision-script -o jsonpath='{.data.create-db-user\.sh}' > /tmp/create-db-user.sh
chmod +x /tmp/create-db-user.sh

# 设置环境变量
export PROJECT_NAME="youngth-guard"
export ENV="dev"
export TARGET_NAMESPACE="dev"
export PGHOST="postgres-lb.infra.svc.cluster.local"
export PGPORT="5432"
export PGUSER="postgres"
export PGPASSWORD="<admin-password>"

# 运行脚本
/tmp/create-db-user.sh
```

---

## 🔄 多环境配置

### 为同一项目创建多个环境

```bash
# Dev 环境
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-provision-youngth-guard-dev
  namespace: infra
spec:
  template:
    spec:
      containers:
        - name: provision
          env:
            - name: PROJECT_NAME
              value: "youngth-guard"
            - name: ENV
              value: "dev"
            - name: TARGET_NAMESPACE
              value: "dev"
          # ... (其他配置同上)
EOF

# Staging 环境
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-provision-youngth-guard-staging
  namespace: infra
spec:
  template:
    spec:
      containers:
        - name: provision
          env:
            - name: PROJECT_NAME
              value: "youngth-guard"
            - name: ENV
              value: "staging"
            - name: TARGET_NAMESPACE
              value: "staging"
          # ... (其他配置同上)
EOF

# Production 环境
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-provision-youngth-guard-prod
  namespace: infra
spec:
  template:
    spec:
      containers:
        - name: provision
          env:
            - name: PROJECT_NAME
              value: "youngth-guard"
            - name: ENV
              value: "prod"
            - name: TARGET_NAMESPACE
              value: "prod"
          # ... (其他配置同上)
EOF
```

---

## 🔐 自定义密码

默认情况下，脚本会自动生成 20 字符的安全密码。如果需要自定义密码：

```bash
# 在 Job 的 env 中添加
- name: DB_PASSWORD
  value: "YourCustomSecurePassword123!"
```

⚠️ **注意：** 自定义密码必须满足强密码要求（见 `docs/db-isolation-spec.md`）

---

## 📊 输出示例

成功执行后，你会看到类似输出：

```
[INFO] ============================================
[INFO] Database Provisioning
[INFO] ============================================
[INFO] Project: youngth-guard
[INFO] Environment: dev
[INFO] Database: youngth_guard_dev
[INFO] User: youngth_guard_dev_user
[INFO] Secret: postgres-youngth-guard-dev (in namespace: dev)
[INFO] ============================================
[INFO] Generating secure password...
[INFO] Password generated (20 characters)
[INFO] Connecting to PostgreSQL at postgres-lb.infra.svc.cluster.local:5432
[INFO] ✓ Connected to PostgreSQL
[INFO] Creating database 'youngth_guard_dev'...
[INFO] ✓ Database 'youngth_guard_dev' created
[INFO] Creating user 'youngth_guard_dev_user'...
[INFO] ✓ User 'youngth_guard_dev_user' created
[INFO] Revoking public permissions on database 'youngth_guard_dev'...
[INFO] ✓ Public permissions revoked
[INFO] Granting permissions to user 'youngth_guard_dev_user'...
[INFO] ✓ CONNECT permission granted
[INFO] ✓ Schema permissions granted
[INFO] ✓ Table permissions granted
[INFO] ✓ Sequence permissions granted
[INFO] ✓ Function permissions granted
[INFO] Verifying permissions...
[INFO] ✓ User can connect and query
[INFO] Creating Kubernetes Secret 'postgres-youngth-guard-dev' in namespace 'dev'...
[INFO] ✓ Secret 'postgres-youngth-guard-dev' created/updated in namespace 'dev'
[INFO] ============================================
[INFO] ✓ Provisioning Completed Successfully
[INFO] ============================================
[INFO] Database: youngth_guard_dev
[INFO] User: youngth_guard_dev_user
[INFO] Secret: postgres-youngth-guard-dev (namespace: dev)
[INFO]
[INFO] Connection Info:
[INFO]   Host: postgres-lb.infra.svc.cluster.local
[INFO]   Port: 5432
[INFO]   Database: youngth_guard_dev
[INFO]   User: youngth_guard_dev_user
[INFO]
[INFO] To use in your application:
[INFO]   kubectl get secret postgres-youngth-guard-dev -n dev -o yaml
[INFO] ============================================
```

---

## ✅ 幂等性验证

脚本可以安全地重复运行：

```bash
# 第一次运行：创建所有资源
kubectl create job test1 --from=job/postgres-provision-youngth-guard-dev -n infra

# 第二次运行：跳过已存在的资源
kubectl create job test2 --from=job/postgres-provision-youngth-guard-dev -n infra

# 结果：
# - 数据库已存在，跳过创建
# - 用户已存在，更新密码
# - Secret 更新
```

---

## 🔍 故障排查

### 问题 1：Job 失败，无法连接到 Postgres

**检查：**
```bash
# 1. 确认 Postgres 正在运行
kubectl -n infra get pods -l app=postgres

# 2. 确认 Service 可用
kubectl -n infra get svc postgres-lb

# 3. 测试网络连接
kubectl run -it --rm nettest --image=postgres:16-alpine --namespace=infra --restart=Never -- \
  pg_isready -h postgres-lb.infra.svc.cluster.local -p 5432
```

### 问题 2：权限不足，无法创建 Secret

**检查：**
```bash
# 1. 确认 ServiceAccount 存在
kubectl -n infra get serviceaccount postgres-provisioner

# 2. 确认 ClusterRole 和 Binding
kubectl get clusterrole postgres-provisioner
kubectl get clusterrolebinding postgres-provisioner

# 3. 验证权限
kubectl auth can-i create secrets --as=system:serviceaccount:infra:postgres-provisioner
```

### 问题 3：Secret 未创建到目标 namespace

**检查：**
```bash
# 1. 确认 namespace 存在
kubectl get namespace dev

# 2. 查看 Job 日志
kubectl -n infra logs job/postgres-provision-youngth-guard-dev

# 3. 手动创建 namespace
kubectl create namespace dev
```

---

## 🧹 清理

### 清理测试 Job

```bash
# 删除特定 Job
kubectl -n infra delete job postgres-provision-youngth-guard-dev

# 删除所有 provisioning Jobs（保留最近3个）
kubectl -n infra delete jobs -l component=provisioning --field-selector status.successful=1

# Jobs 会在 24 小时后自动清理（ttlSecondsAfterFinished）
```

### 删除数据库和用户

⚠️ **危险操作！** 会删除所有数据

```bash
# 连接到 Postgres
kubectl -n infra exec -it postgres-0 -- psql -U postgres

# 删除数据库（会断开所有连接）
DROP DATABASE youngth_guard_dev;

# 删除用户
DROP USER youngth_guard_dev_user;

# 删除 Secret
kubectl -n dev delete secret postgres-youngth-guard-dev
```

---

## 📚 集成到 GitOps

### 在 ArgoCD Application 中使用

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: youngth-guard-backend
  namespace: argocd
spec:
  # ... 其他配置

  # PreSync Hook: 确保数据库存在
  syncPolicy:
    syncOptions:
      - CreateNamespace=true

  # 注意：由于 Job 需要手动配置项目名和环境
  # 建议在首次部署前手动运行 provisioning Job
  # 或者在 CI/CD 流程中自动化
```

---

## 🎯 最佳实践

1. **首次部署时运行** - 在应用首次部署前创建数据库
2. **一个 Job 一个环境** - 不要共享 Job，每个环境独立
3. **保留 Job 历史** - 便于审计和回溯
4. **定期审计** - 检查数据库和用户列表，清理不用的资源
5. **密码轮换** - 定期运行 Job 更新密码（会自动更新 Secret）

---

## 📖 相关文档

- `docs/db-isolation-spec.md` - 数据库隔离规范
- `infra/postgres/README.md` - Postgres 部署文档
- `infra/postgres/backup/README.md` - 备份恢复文档
