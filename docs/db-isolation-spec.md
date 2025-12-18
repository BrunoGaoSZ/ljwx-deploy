# 数据库复用与隔离规范

## 📋 规范目标

本规范定义了如何在共享的 infra Postgres 实例中安全地隔离多个项目的数据，确保：

1. **数据隔离** - 项目之间无法访问彼此的数据
2. **权限最小化** - 应用只能访问自己需要的数据库
3. **命名统一** - 便于管理和审计
4. **可扩展** - 支持多项目、多环境

---

## 🏷️ 命名规范

### 数据库命名规范

**格式：** `{project}_{env}`

**规则：**
- 全部小写
- 使用下划线分隔
- 项目名简短清晰（推荐 2-4 个单词）
- 环境名固定为：`dev` / `staging` / `prod`

**示例：**
```
youngth_guard_dev        ✅ 正确
youngth_guard_staging    ✅ 正确
youngth_guard_prod       ✅ 正确

YoungthGuard_Dev         ❌ 错误（大小写混合）
youngth-guard-dev        ❌ 错误（使用连字符）
yg_dev                   ❌ 不推荐（缩写不清晰）
```

---

### 用户命名规范

**格式：** `{project}_{env}_user`

**规则：**
- 与数据库名对应，添加 `_user` 后缀
- 全部小写
- 每个数据库有独立的用户
- 不使用超级用户或 postgres 用户

**示例：**
```
youngth_guard_dev_user      ✅ 正确
youngth_guard_staging_user  ✅ 正确
youngth_guard_prod_user     ✅ 正确

youngth_guard_user          ❌ 错误（缺少环境标识）
admin                       ❌ 错误（不清晰）
postgres                    ❌ 禁止（超级用户）
```

---

### Secret 命名规范

**格式：** `postgres-{project}-{env}`

**规则：**
- 使用连字符分隔（Kubernetes Secret 命名约定）
- 创建在应用的 namespace 中
- 包含完整的连接信息

**示例：**
```
postgres-youngth-guard-dev      ✅ 正确
postgres-youngth-guard-staging  ✅ 正确
postgres-youngth-guard-prod     ✅ 正确

youngth-guard-db                ❌ 错误（缺少 postgres 前缀）
db-secret                       ❌ 错误（不清晰）
```

---

## 🔒 权限最小化原则

### 应用用户权限清单

**允许的权限：**
- ✅ 连接到指定数据库：`CONNECT`
- ✅ 创建 Schema：`CREATE`（在自己的数据库内）
- ✅ 在 public schema 中操作：`USAGE`, `CREATE`
- ✅ 表的所有权限：`SELECT`, `INSERT`, `UPDATE`, `DELETE`
- ✅ 序列权限：`USAGE`, `SELECT`, `UPDATE`

**禁止的权限：**
- ❌ 超级用户权限：`SUPERUSER`
- ❌ 创建角色：`CREATEROLE`
- ❌ 创建数据库：`CREATEDB`
- ❌ 复制权限：`REPLICATION`
- ❌ 访问其他数据库

### 标准权限 SQL 模板

```sql
-- 1. 创建数据库
CREATE DATABASE {project}_{env};

-- 2. 创建用户（密码应该使用强密码）
CREATE USER {project}_{env}_user WITH PASSWORD 'SecurePassword123!';

-- 3. 撤销默认权限
REVOKE ALL ON DATABASE {project}_{env} FROM PUBLIC;

-- 4. 授予连接权限
GRANT CONNECT ON DATABASE {project}_{env} TO {project}_{env}_user;

-- 5. 连接到目标数据库
\c {project}_{env}

-- 6. 授予 Schema 权限
GRANT USAGE, CREATE ON SCHEMA public TO {project}_{env}_user;

-- 7. 授予表权限（包括未来创建的表）
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {project}_{env}_user;

-- 8. 授予序列权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {project}_{env}_user;

-- 9. 授予函数执行权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT EXECUTE ON FUNCTIONS TO {project}_{env}_user;
```

---

## 🔐 Secret 内容规范

### Secret 必须包含的字段

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-{project}-{env}
  namespace: {app-namespace}
  labels:
    app: {project}
    env: {env}
    db-provider: infra-postgres
type: Opaque
stringData:
  # 必须字段
  POSTGRES_HOST: postgres-lb.infra.svc.cluster.local
  POSTGRES_PORT: "5432"
  POSTGRES_DB: {project}_{env}
  POSTGRES_USER: {project}_{env}_user
  POSTGRES_PASSWORD: {secure-password}

  # 可选：完整连接字符串
  DATABASE_URL: postgresql://{project}_{env}_user:{password}@postgres-lb.infra.svc.cluster.local:5432/{project}_{env}
```

### 密码要求

**强密码规则：**
- 至少 16 字符
- 包含大小写字母
- 包含数字
- 包含特殊字符
- 不包含项目名或常见词汇
- 每个环境使用不同密码

**生成密码示例：**
```bash
# 生成安全随机密码
openssl rand -base64 24
```

---

## 📝 完整示例：youngth-guard 项目

### 场景说明

项目名称：youngth-guard（留守儿童心理风险感知平台）
环境：dev, staging, prod
应用 Namespace：dev, staging, prod

---

### 示例 1：创建 dev 环境数据库

#### Step 1: 在 Postgres 中创建数据库和用户

```bash
# 连接到 Postgres
kubectl -n infra exec -it postgres-0 -- psql -U postgres

# 执行以下 SQL
```

```sql
-- 1. 创建数据库
CREATE DATABASE youngth_guard_dev;

-- 2. 创建用户（使用强密码）
CREATE USER youngth_guard_dev_user WITH PASSWORD 'YgDev2025!SecureP@ssw0rd';

-- 3. 撤销 PUBLIC 权限
REVOKE ALL ON DATABASE youngth_guard_dev FROM PUBLIC;

-- 4. 授予连接权限
GRANT CONNECT ON DATABASE youngth_guard_dev TO youngth_guard_dev_user;

-- 5. 连接到新数据库
\c youngth_guard_dev

-- 6. 授予 Schema 权限
GRANT USAGE, CREATE ON SCHEMA public TO youngth_guard_dev_user;

-- 7. 授予表权限（包括未来创建的表）
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO youngth_guard_dev_user;

-- 8. 授予序列权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO youngth_guard_dev_user;

-- 9. 授予函数执行权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT EXECUTE ON FUNCTIONS TO youngth_guard_dev_user;

-- 10. 验证权限
\l youngth_guard_dev
\du youngth_guard_dev_user
```

#### Step 2: 创建 Kubernetes Secret

```bash
# 在 dev namespace 创建 Secret
kubectl create secret generic postgres-youngth-guard-dev \
  --namespace=dev \
  --from-literal=POSTGRES_HOST=postgres-lb.infra.svc.cluster.local \
  --from-literal=POSTGRES_PORT=5432 \
  --from-literal=POSTGRES_DB=youngth_guard_dev \
  --from-literal=POSTGRES_USER=youngth_guard_dev_user \
  --from-literal=POSTGRES_PASSWORD='YgDev2025!SecureP@ssw0rd' \
  --from-literal=DATABASE_URL='postgresql://youngth_guard_dev_user:YgDev2025!SecureP@ssw0rd@postgres-lb.infra.svc.cluster.local:5432/youngth_guard_dev'

# 添加标签
kubectl label secret postgres-youngth-guard-dev \
  -n dev \
  app=youngth-guard \
  env=dev \
  db-provider=infra-postgres
```

#### Step 3: 在应用中使用 Secret

**Deployment 配置示例：**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: youngth-guard-backend
  namespace: dev
spec:
  template:
    spec:
      containers:
        - name: backend
          image: ghcr.io/brunogaosz/youngth-guard-backend:latest
          env:
            # 方式 1：单独环境变量
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

            # 方式 2：完整连接字符串
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: DATABASE_URL
```

#### Step 4: 验证连接

```bash
# 测试从应用 Pod 连接数据库
kubectl run -it --rm psql-test \
  --image=postgres:16-alpine \
  --namespace=dev \
  --env="PGHOST=postgres-lb.infra.svc.cluster.local" \
  --env="PGPORT=5432" \
  --env="PGDATABASE=youngth_guard_dev" \
  --env="PGUSER=youngth_guard_dev_user" \
  --env="PGPASSWORD=YgDev2025!SecureP@ssw0rd" \
  --restart=Never \
  -- psql -c "SELECT current_database(), current_user;"

# 预期输出：
#  current_database  |       current_user
# -------------------+--------------------------
#  youngth_guard_dev | youngth_guard_dev_user
```

---

### 示例 2：staging 和 prod 环境

**遵循相同模式，只需修改环境标识：**

```sql
-- Staging
CREATE DATABASE youngth_guard_staging;
CREATE USER youngth_guard_staging_user WITH PASSWORD 'YgStaging2025!DifferentP@ss';
-- ... 授权步骤相同 ...

-- Production
CREATE DATABASE youngth_guard_prod;
CREATE USER youngth_guard_prod_user WITH PASSWORD 'YgProd2025!AnotherSecureP@ss';
-- ... 授权步骤相同 ...
```

```bash
# Staging Secret
kubectl create secret generic postgres-youngth-guard-staging -n staging ...

# Production Secret
kubectl create secret generic postgres-youngth-guard-prod -n prod ...
```

---

## ✅ 规范检查清单

### 创建新项目数据库前必须确认

- [ ] 数据库名称符合 `{project}_{env}` 格式
- [ ] 用户名称符合 `{project}_{env}_user` 格式
- [ ] 密码符合强密码要求（16+ 字符，包含大小写数字特殊字符）
- [ ] 已撤销 PUBLIC 权限
- [ ] 仅授予必要的权限（CONNECT, USAGE, CRUD）
- [ ] 未授予 SUPERUSER / CREATEROLE / CREATEDB 权限
- [ ] Secret 名称符合 `postgres-{project}-{env}` 格式
- [ ] Secret 创建在正确的 namespace
- [ ] Secret 包含所有必需字段
- [ ] 已验证应用可以连接

---

## 🔍 权限审计

### 定期审计命令

```sql
-- 1. 列出所有数据库和所有者
SELECT datname, pg_catalog.pg_get_userbyid(datdba) as owner
FROM pg_catalog.pg_database
WHERE datname NOT IN ('postgres', 'template0', 'template1')
ORDER BY datname;

-- 2. 列出所有非系统用户
SELECT usename, usesuper, usecreatedb, usecreaterole
FROM pg_catalog.pg_user
WHERE usename NOT IN ('postgres', 'replication')
ORDER BY usename;

-- 3. 检查危险权限（应该为空）
SELECT usename
FROM pg_catalog.pg_user
WHERE (usesuper = true OR usecreatedb = true OR usecreaterole = true)
  AND usename != 'postgres';

-- 4. 查看特定用户权限
SELECT grantee, privilege_type
FROM information_schema.table_privileges
WHERE grantee = 'youngth_guard_dev_user'
  AND table_schema = 'public'
LIMIT 10;
```

---

## 🚫 禁止行为

以下操作严格禁止：

1. ❌ **使用 postgres 超级用户连接应用**
   - 原因：权限过大，安全风险

2. ❌ **应用用户访问其他数据库**
   - 原因：破坏隔离性

3. ❌ **在代码中硬编码密码**
   - 原因：安全风险，密码泄露

4. ❌ **多个项目共享同一个数据库**
   - 原因：无法独立管理，迁移困难

5. ❌ **在 public schema 外创建对象**
   - 原因：权限管理复杂化

6. ❌ **手动修改 Secret（绕过 GitOps）**
   - 原因：配置漂移，无法追踪

---

## 📊 多项目示例矩阵

| 项目 | 环境 | 数据库名 | 用户名 | Secret 名 | Namespace |
|------|------|---------|--------|----------|-----------|
| youngth-guard | dev | youngth_guard_dev | youngth_guard_dev_user | postgres-youngth-guard-dev | dev |
| youngth-guard | staging | youngth_guard_staging | youngth_guard_staging_user | postgres-youngth-guard-staging | staging |
| youngth-guard | prod | youngth_guard_prod | youngth_guard_prod_user | postgres-youngth-guard-prod | prod |
| other-project | dev | other_project_dev | other_project_dev_user | postgres-other-project-dev | dev |
| api-gateway | prod | api_gateway_prod | api_gateway_prod_user | postgres-api-gateway-prod | prod |

---

## 🛠️ 故障排查

### 常见问题

#### 问题 1：应用无法连接数据库

**排查步骤：**
```bash
# 1. 检查 Secret 是否存在
kubectl -n dev get secret postgres-youngth-guard-dev

# 2. 验证 Secret 内容
kubectl -n dev get secret postgres-youngth-guard-dev -o yaml

# 3. 测试网络连接
kubectl run -it --rm nettest \
  --image=postgres:16-alpine \
  --namespace=dev \
  --restart=Never \
  -- pg_isready -h postgres-lb.infra.svc.cluster.local -p 5432

# 4. 测试认证
kubectl run -it --rm psql-test \
  --image=postgres:16-alpine \
  --namespace=dev \
  --restart=Never \
  -- psql -h postgres-lb.infra.svc.cluster.local -U youngth_guard_dev_user -d youngth_guard_dev -c "SELECT 1;"
```

#### 问题 2：权限不足错误

**排查步骤：**
```sql
-- 连接到数据库
\c youngth_guard_dev

-- 检查当前用户
SELECT current_user, current_database();

-- 检查 Schema 权限
SELECT schema_name, schema_owner
FROM information_schema.schemata
WHERE schema_name = 'public';

-- 检查表权限
\dp
```

**解决方案：**
```sql
-- 重新授予权限
GRANT USAGE, CREATE ON SCHEMA public TO youngth_guard_dev_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO youngth_guard_dev_user;
```

---

## 📚 参考资料

- PostgreSQL 官方文档：权限管理
  https://www.postgresql.org/docs/16/user-manag.html

- Kubernetes Secrets 最佳实践
  https://kubernetes.io/docs/concepts/configuration/secret/

- 本平台相关文档：
  - `docs/architecture-overview.md` - 平台架构说明
  - `infra/postgres/README.md` - Postgres 部署文档
  - `infra/postgres/backup/README.md` - 备份恢复文档
