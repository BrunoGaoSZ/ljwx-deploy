# 数据库升级 & 回滚操作手册

## 📋 概述

本文档提供数据库迁移的标准操作流程，确保升级和回滚操作的安全性和可逆性。

**核心原则：**
- ✅ 所有操作都必须可逆
- ✅ 优先选择向前修复（Rollforward），而非回滚（Rollback）
- ✅ 回滚应用 ≠ 回滚数据库
- ✅ PITR 是最后手段，不是常规操作

---

## 🎯 决策树：出现问题时该怎么办

```
检测到问题
  ↓
是否是数据库迁移导致？
  ├─ 否 → 回滚应用代码（K8s Deployment）
  │         数据库保持不变
  │
  └─ 是 → 迁移是否已部分成功？
          ├─ 完全失败 → 修复迁移 SQL → 重新执行
          │              数据库状态未变
          │
          └─ 部分成功 → 数据是否已损坏/丢失？
                      ├─ 否 → 编写修复迁移（Rollforward）
                      │        ↓
                      │      V{N+1}__fix_migration_vN.sql
                      │
                      └─ 是 → 触发 PITR 恢复
                               ⚠️ 需要审批 + 数据丢失风险
```

---

## 📦 STEP 1: 升级前准备

### 1.1 Pre-Flight Checklist

```bash
# ============================================
# 升级前检查清单
# ============================================

# 1. 确认迁移文件已合并到主分支
git log --oneline -5
git diff main origin/main

# 2. 检查 Flyway 迁移文件命名
ls -la backend-fastapi/migrations/
# 预期：V1__, V2__, V3__ ... 连续且符合规范

# 3. 在本地/测试环境验证迁移
cd backend-fastapi
flyway -url=jdbc:postgresql://localhost:5432/test_db \
       -user=test_user \
       -password=test_pass \
       -locations=filesystem:./migrations \
       migrate

# 4. 检查迁移是否幂等
# 再次执行，应该显示 "No migrations to apply"
flyway migrate

# 5. 检查生产数据库状态
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT version, description, installed_on, success FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5;"

# 6. 确认备份最新
kubectl -n infra get cronjob
kubectl -n infra logs -l app=pgbackrest --tail=50

# 7. 查看最近的备份时间
kubectl -n infra exec postgres-0 -- \
  pgbackrest --stanza=main info

# 8. 确认当前没有长时间运行的事务（可能导致锁等待）
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT pid, usename, application_name, state, query_start, query
   FROM pg_stat_activity
   WHERE state != 'idle'
   ORDER BY query_start;"
```

**通过标准：**
- ✅ 迁移在测试环境成功执行
- ✅ 备份在最近 24 小时内完成
- ✅ 无长时间运行的查询（> 30 分钟）
- ✅ 迁移执行时间 < 5 分钟（如果 > 5 分钟，考虑维护窗口）

### 1.2 手动触发完整备份（推荐）

```bash
# 在升级前手动触发一次完整备份
kubectl -n infra create job --from=cronjob/pgbackrest-full-backup \
  manual-backup-before-migration-$(date +%Y%m%d%H%M%S)

# 等待备份完成
kubectl -n infra wait --for=condition=complete --timeout=600s \
  job/manual-backup-before-migration-$(date +%Y%m%d%H%M%S)

# 检查备份状态
kubectl -n infra logs job/manual-backup-before-migration-$(date +%Y%m%d%H%M%S)
```

### 1.3 通知相关人员

- [ ] 通知团队即将执行数据库迁移
- [ ] 预估迁移时间窗口
- [ ] 准备回滚预案（如果需要）

---

## 🚀 STEP 2: 执行升级

### 2.1 自动执行（通过 ArgoCD PreSync）

**标准流程：**

```bash
# 1. CI 构建新镜像并推送
# 2. CI 更新 GitOps 仓库中的镜像 tag
git pull origin main

# 3. ArgoCD 检测到变化，自动触发 Sync
# 4. PreSync Hook 执行数据库迁移
# 5. 迁移成功 → 部署新应用
# 6. 迁移失败 → 阻止部署

# 监控 ArgoCD Sync 进度
kubectl -n argocd get application youngth-guard-backend -w

# 查看 PreSync Job 日志
kubectl -n dev logs -l component=migration -f --tail=100

# 查看迁移历史
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT version, description, installed_on, success FROM flyway_schema_history ORDER BY installed_rank;"
```

### 2.2 手动执行（紧急情况/测试）

```bash
# 1. 手动创建迁移 Job（移除 PreSync Hook 注解）
kubectl -n dev apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration-manual-$(date +%Y%m%d%H%M%S)
  namespace: dev
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app: youngth-guard-backend
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
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_HOST
            - name: POSTGRES_PORT
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_PORT
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_USER
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_PASSWORD
      containers:
        - name: flyway
          image: flyway/flyway:10-alpine
          command:
            - /bin/sh
            - -c
            - |
              set -e
              echo "Running migrations..."
              flyway -connectRetries=3 migrate
              echo "Migration completed!"
              flyway info
          env:
            - name: FLYWAY_URL
              value: "jdbc:postgresql://\$(POSTGRES_HOST):\$(POSTGRES_PORT)/\$(POSTGRES_DB)"
            - name: FLYWAY_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_USER
            - name: FLYWAY_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-youngth-guard-dev
                  key: POSTGRES_PASSWORD
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
            - name: FLYWAY_BASELINE_ON_MIGRATE
              value: "true"
            - name: FLYWAY_BASELINE_VERSION
              value: "0"
            - name: FLYWAY_OUT_OF_ORDER
              value: "false"
            - name: FLYWAY_VALIDATE_ON_MIGRATE
              value: "true"
          volumeMounts:
            - name: migrations
              mountPath: /flyway/sql
              readOnly: true
      volumes:
        - name: migrations
          configMap:
            name: db-migrations
EOF

# 2. 查看 Job 日志
kubectl -n dev logs -f job/db-migration-manual-$(date +%Y%m%d%H%M%S)

# 3. 验证迁移成功
kubectl -n dev get job db-migration-manual-$(date +%Y%m%d%H%M%S)
```

### 2.3 升级后验证

```bash
# 1. 检查迁移 Job 状态
kubectl -n dev get job -l component=migration

# 预期输出：
# NAME           COMPLETIONS   DURATION   AGE
# db-migration   1/1           15s        2m

# 2. 验证 Flyway 历史
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT version, description, installed_on, success FROM flyway_schema_history ORDER BY installed_rank;"

# 预期：所有迁移 success = true

# 3. 检查应用 Pod 状态
kubectl -n dev get pods -l app=youngth-guard-backend

# 预期：所有 Pod Running，Ready 1/1

# 4. 查看应用日志
kubectl -n dev logs -l app=youngth-guard-backend --tail=50

# 预期：无数据库连接错误

# 5. 执行冒烟测试
curl -X GET https://dev.youngth-guard.example.com/health
# 预期：{"status": "ok"}

# 6. 验证数据库表结构
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "\dt"  # 列出所有表

kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "\d users"  # 查看 users 表结构
```

**验证通过标准：**
- ✅ 迁移 Job 成功完成（COMPLETIONS 1/1）
- ✅ Flyway 历史中所有迁移 success = true
- ✅ 应用 Pod 全部 Running
- ✅ 应用日志无错误
- ✅ 健康检查接口返回正常

---

## ⏮️ STEP 3: 回滚策略

### 3.1 场景 1：应用代码有 Bug，数据库迁移成功

**问题：** 新版本应用有功能性 Bug，但数据库迁移已成功。

**策略：回滚应用，保留数据库**

```bash
# ============================================
# 回滚应用到上一个版本
# ============================================

# 方法 1：通过 ArgoCD 回滚
kubectl -n argocd patch application youngth-guard-backend \
  --type merge \
  -p '{"operation": {"sync": {"revision": "previous-commit-sha"}}}'

# 方法 2：通过 Kubectl 回滚 Deployment
kubectl -n dev rollout undo deployment/youngth-guard-backend

# 方法 3：手动更新镜像 tag
cd ljwx-deploy
git revert HEAD  # 撤销最新的镜像 tag 更新
git push origin main

# ArgoCD 自动检测并回滚应用

# 验证回滚
kubectl -n dev rollout status deployment/youngth-guard-backend
kubectl -n dev get pods -l app=youngth-guard-backend
```

**重要：**
- ❌ **不要回滚数据库迁移**
- ✅ 旧版本应用代码必须兼容新数据库 Schema（这就是 Expand/Contract 的意义）
- ✅ 如果旧代码不兼容，编写修复迁移（Rollforward）

### 3.2 场景 2：数据库迁移失败，数据库状态未变

**问题：** Flyway 迁移执行失败，数据库保持原状态。

**策略：修复迁移 SQL，重新执行**

```bash
# ============================================
# 场景：V5 迁移失败
# ============================================

# 1. 查看失败的迁移
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT * FROM flyway_schema_history WHERE success = false;"

# 输出示例：
# installed_rank | version | description      | success
# 5              | 5       | add_email_column | false

# 2. 查看错误日志
kubectl -n dev logs -l component=migration --tail=100

# 3. 修复迁移文件
# 编辑 backend-fastapi/migrations/V5__add_email_column.sql
# 修复 SQL 语法错误

# 4. 删除失败记录（让 Flyway 重新尝试）
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "DELETE FROM flyway_schema_history WHERE version = '5' AND success = false;"

# 5. 重新执行迁移
kubectl -n dev delete job db-migration  # 删除旧 Job
# ArgoCD 会自动重新创建 PreSync Job

# 或手动触发
argocd app sync youngth-guard-backend --prune

# 6. 验证迁移成功
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT * FROM flyway_schema_history WHERE version = '5';"
```

### 3.3 场景 3：数据库迁移部分成功，数据未损坏

**问题：** V5 迁移执行了一部分后失败，数据库处于中间状态但数据未丢失。

**策略：Rollforward（编写修复迁移）**

```bash
# ============================================
# 场景：V5 添加了列但未创建索引就失败了
# ============================================

# 1. 评估当前数据库状态
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "\d users"

# 发现：email 列已添加，但缺少索引

# 2. 标记 V5 为失败（如果未自动标记）
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "UPDATE flyway_schema_history SET success = false WHERE version = '5';"

# 3. 编写修复迁移
# 创建 backend-fastapi/migrations/V6__fix_v5_migration.sql
cat > backend-fastapi/migrations/V6__fix_v5_migration.sql <<'EOF'
-- ============================================
-- Migration: V6__fix_v5_migration
-- Description: 修复 V5 迁移中断导致的缺失索引
-- ============================================

-- 创建缺失的索引（幂等）
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 验证数据完整性
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_users_email') THEN
        RAISE EXCEPTION 'Index idx_users_email still missing!';
    END IF;
END $$;
EOF

# 4. 删除 V5 失败记录
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "DELETE FROM flyway_schema_history WHERE version = '5';"

# 5. 提交修复并部署
git add backend-fastapi/migrations/V6__fix_v5_migration.sql
git commit -m "fix: V6 修复 V5 迁移中断"
git push origin main

# 6. ArgoCD 自动执行 V6 迁移
```

**原则：**
- ✅ **优先选择 Rollforward**（向前修复）
- ✅ 编写 V{N+1} 修复 V{N} 的问题
- ❌ **不要直接修改已执行的迁移文件**
- ❌ **不要手动修改数据库 Schema**

### 3.4 场景 4：数据损坏或丢失 → 触发 PITR

**问题：** 迁移导致数据损坏或意外删除。

**⚠️ 警告：这是最后手段，会丢失 PITR 时间点之后的数据！**

**前提条件：**
- [ ] 数据已损坏且无法通过 SQL 修复
- [ ] 业务方批准数据丢失风险
- [ ] 已评估 PITR 后需要手动补录的数据量
- [ ] 确认 PITR 目标时间点的备份存在

**执行步骤：**

```bash
# ============================================
# PITR 恢复到迁移前的时间点
# ============================================

# 1. 确定目标时间点（迁移开始前）
TARGET_TIME="2025-01-18 10:30:00"

# 2. 停止应用（防止新数据写入）
kubectl -n dev scale deployment/youngth-guard-backend --replicas=0

# 3. 停止 Postgres StatefulSet
kubectl -n infra scale statefulset postgres --replicas=0

# 4. 创建 PITR 恢复 Job
cat > /tmp/pitr-restore.yaml <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-pitr-restore
  namespace: infra
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: pgbackrest
          image: pgbackrest/pgbackrest:latest
          command:
            - /bin/bash
            - -c
            - |
              set -e
              echo "Starting PITR restore to ${TARGET_TIME}"

              # 恢复到指定时间点
              pgbackrest --stanza=main \
                         --type=time \
                         --target="${TARGET_TIME}" \
                         --delta \
                         restore

              echo "PITR restore completed!"
          env:
            - name: TARGET_TIME
              value: "${TARGET_TIME}"
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
            - name: backup
              mountPath: /backup
            - name: pgbackrest-config
              mountPath: /etc/pgbackrest
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-data-postgres-0
        - name: backup
          persistentVolumeClaim:
            claimName: pgbackrest-backup
        - name: pgbackrest-config
          configMap:
            name: pgbackrest-config
EOF

kubectl apply -f /tmp/pitr-restore.yaml

# 5. 等待恢复完成
kubectl -n infra wait --for=condition=complete --timeout=1800s job/postgres-pitr-restore

# 6. 查看恢复日志
kubectl -n infra logs job/postgres-pitr-restore

# 7. 启动 Postgres
kubectl -n infra scale statefulset postgres --replicas=1

# 8. 等待 Postgres 就绪
kubectl -n infra wait --for=condition=ready pod/postgres-0 --timeout=300s

# 9. 验证数据库状态
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT version, description, installed_on FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5;"

# 10. 验证业务数据
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT count(*) FROM users;"

# 11. 清理失败的迁移记录
# 根据 Flyway 历史决定是否需要删除失败的迁移记录

# 12. 重新启动应用（使用旧版本镜像）
kubectl -n dev scale deployment/youngth-guard-backend --replicas=3

# 13. 验证应用功能
kubectl -n dev get pods -l app=youngth-guard-backend
curl https://dev.youngth-guard.example.com/health
```

**PITR 后操作：**
- [ ] 评估丢失的数据（PITR 时间点之后的写入）
- [ ] 手动补录关键数据
- [ ] 修复导致问题的迁移文件
- [ ] 在测试环境重新验证修复后的迁移
- [ ] 部署修复后的迁移

---

## 🚫 禁止行为清单

### 迁移期间绝对禁止的操作

1. **❌ 直接在生产数据库执行 DDL**
   ```sql
   -- 禁止！
   psql -U postgres -d youngth_guard_prod
   ALTER TABLE users ADD COLUMN ...;
   ```
   **正确做法：** 所有 Schema 变更必须通过 Flyway 迁移文件

2. **❌ 修改已执行的迁移文件**
   ```bash
   # 禁止！
   vim backend-fastapi/migrations/V3__add_column.sql  # V3 已执行
   git commit -m "fix V3"
   ```
   **正确做法：** 创建新的 V4 修复 V3 的问题

3. **❌ 手动修改 `flyway_schema_history` 表（非紧急情况）**
   ```sql
   -- 禁止！（除非明确知道后果）
   UPDATE flyway_schema_history SET success = true WHERE version = '5';
   ```
   **正确做法：** 删除失败记录，修复 SQL，重新执行

4. **❌ 在迁移中执行大规模数据修改（无批量处理）**
   ```sql
   -- 禁止！会锁表很久
   UPDATE users SET status = 'active';  -- 100万行
   ```
   **正确做法：** 使用批量处理（参考 `docs/flyway-guide/README.md`）

5. **❌ 在迁移中删除表/列（无 Expand/Contract）**
   ```sql
   -- 禁止！
   DROP TABLE old_table;
   ALTER TABLE users DROP COLUMN old_field;
   ```
   **正确做法：** 先重命名为 `_deprecated`，等待几个版本后再删除

6. **❌ 回滚数据库迁移（非 PITR 场景）**
   ```bash
   # 禁止！
   kubectl -n infra exec postgres-0 -- \
     psql -U postgres -d youngth_guard_dev -c \
     "ALTER TABLE users DROP COLUMN email;"  # 试图"撤销" V5
   ```
   **正确做法：** 使用 Expand/Contract 模式，或编写修复迁移

7. **❌ 在高峰期执行耗时迁移**
   ```bash
   # 禁止！
   # 14:00 (业务高峰) 执行需要 10 分钟的迁移
   ```
   **正确做法：** 在凌晨低峰期执行，或使用在线 Schema 变更工具

8. **❌ 未备份就执行高风险迁移**
   ```bash
   # 禁止！
   # 没有检查备份就执行 DROP/TRUNCATE
   ```
   **正确做法：** 先验证最近备份，必要时手动触发完整备份

9. **❌ 跳过测试环境直接在生产执行**
   ```bash
   # 禁止！
   # 新迁移文件直接部署到生产
   ```
   **正确做法：** dev → staging → prod 逐级验证

10. **❌ 在迁移失败时继续部署应用**
    ```bash
    # 禁止！
    kubectl -n dev set image deployment/youngth-guard-backend \
      backend=ghcr.io/brunogaosz/youngth-guard-backend:v2  # 迁移失败时强制部署
    ```
    **正确做法：** 修复迁移后再部署，或回滚应用到旧版本

---

## 📋 快速参考卡

### 常见场景速查表

| 场景 | 策略 | 操作 |
|------|------|------|
| 应用 Bug，DB 正常 | 回滚应用 | `kubectl rollout undo deployment/xxx` |
| 迁移完全失败 | 修复 SQL 重试 | 删除失败记录 → 修复文件 → 重新执行 |
| 迁移部分成功 | Rollforward | 编写 V{N+1} 修复迁移 |
| 数据损坏 | PITR | 恢复到迁移前时间点 |
| 迁移太慢 | 批量处理 | 参考 Flyway 指南中的批量更新示例 |
| 需要回滚 Schema | Expand/Contract | 先部署代码兼容 → 再删除旧 Schema |

### 故障排查命令速查

```bash
# 查看迁移历史
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT * FROM flyway_schema_history ORDER BY installed_rank;"

# 查看迁移 Job 日志
kubectl -n dev logs -l component=migration --tail=100

# 检查应用状态
kubectl -n dev get pods -l app=youngth-guard-backend
kubectl -n dev logs -l app=youngth-guard-backend --tail=50

# 查看最近备份
kubectl -n infra exec postgres-0 -- pgbackrest --stanza=main info

# 检查长时间运行的查询
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c \
  "SELECT pid, usename, query_start, state, query FROM pg_stat_activity WHERE state != 'idle';"

# 检查表结构
kubectl -n infra exec postgres-0 -- \
  psql -U postgres -d youngth_guard_dev -c "\d table_name"

# 回滚应用
kubectl -n dev rollout undo deployment/youngth-guard-backend

# 手动触发备份
kubectl -n infra create job --from=cronjob/pgbackrest-full-backup manual-backup-$(date +%Y%m%d%H%M%S)
```

---

## 📞 升级失败联系流程

1. **立即操作：**
   - 停止继续部署（如果尚未完成）
   - 截图错误日志
   - 记录时间点

2. **评估影响：**
   - 业务功能是否受影响？
   - 数据是否损坏？
   - 用户是否受影响？

3. **根据决策树选择策略：**
   - 应用 Bug → 回滚应用
   - 迁移失败 → 修复重试
   - 数据损坏 → 联系 DBA + PITR

4. **事后复盘：**
   - 记录故障原因
   - 更新测试用例
   - 改进迁移流程

---

## 📖 相关文档

- `docs/flyway-guide/README.md` - Flyway 规范和 Expand/Contract 模式
- `docs/argocd-migration/README.md` - PreSync Hook 工作流程
- `infra/postgres/backup/README.md` - 备份和 PITR 详细步骤
- `docs/architecture-overview.md` - 平台架构说明
