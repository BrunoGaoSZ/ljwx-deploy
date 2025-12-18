# PostgreSQL 备份与 Point-In-Time Recovery (PITR)

## 📋 备份策略

### 备份类型

| 类型 | 频率 | 保留期 | 说明 |
|------|------|--------|------|
| **Full (全量)** | 每天 2:00 AM | 4 个 | 完整数据库备份 |
| **Diff (差异)** | 每 6 小时 | 2 个 | 相对于最近 Full 备份的变化 |
| **WAL (归档)** | 持续 | 与 Full 备份对应 | 用于 PITR |

### 为什么选择 pgBackRest？

1. **成熟稳定** - PostgreSQL 社区推荐的备份工具
2. **支持 PITR** - 完整的 WAL 归档和恢复
3. **增量备份** - 节省存储空间和备份时间
4. **并行备份** - 支持多线程，速度快
5. **验证功能** - 可以验证备份完整性

---

## 🚀 部署备份系统

### 1. 部署备份配置

```bash
# 部署备份相关资源
kubectl apply -k infra/postgres/backup/

# 验证 CronJob
kubectl -n infra get cronjob

# 验证 PVC
kubectl -n infra get pvc pgbackrest-repo
```

### 2. 手动触发首次全量备份

```bash
# 创建 Job 从 CronJob
kubectl create job -n infra postgres-backup-init \
  --from=cronjob/postgres-backup-full

# 查看备份进度
kubectl -n infra logs -f job/postgres-backup-init

# 检查备份状态
kubectl -n infra wait --for=condition=complete job/postgres-backup-init --timeout=600s
```

### 3. 验证备份

```bash
# 查看备份信息
kubectl -n infra exec postgres-0 -- \
  pgbackrest --stanza=postgres info

# 预期输出示例：
# stanza: postgres
#     status: ok
#     cipher: none
#
#     db (current)
#         wal archive min/max (16): 000000010000000000000001/000000010000000000000003
#
#         full backup: 20251218-020000F
#             timestamp start/stop: 2025-12-18 02:00:00 / 2025-12-18 02:05:00
#             wal start/stop: 000000010000000000000002 / 000000010000000000000002
#             database size: 25.1MB, database backup size: 25.1MB
#             repo1: backup set size: 3.2MB, backup size: 3.2MB
```

---

## 🔄 Point-In-Time Recovery (PITR) 操作文档

### 概念说明

**PITR 允许你恢复到任意时间点**，而不仅仅是最近的备份。

**适用场景：**
- 误删除数据（DELETE / DROP TABLE）
- 错误的数据更新（UPDATE 错误）
- 应用 bug 导致数据损坏
- 需要回到某个已知的正确状态

**注意事项：**
⚠️ **PITR 会丢失恢复点之后的所有数据**
⚠️ **必须先停止 Postgres 服务**
⚠️ **操作前务必做好现有数据的备份**

---

## 📖 PITR 完整演练流程

### 场景：恢复到 2025-12-18 10:30:00

假设在 10:35:00 发现数据被误删除，需要恢复到 10:30:00。

---

### Step 1: 确认目标恢复时间

```bash
# 1.1 确认当前时间和事故时间
echo "当前时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "目标恢复时间: 2025-12-18 10:30:00"

# 1.2 检查是否有可用的备份
kubectl -n infra exec postgres-0 -- \
  pgbackrest --stanza=postgres info

# 1.3 验证 WAL 归档覆盖目标时间
# 确保 wal archive max 时间晚于目标恢复时间
```

---

### Step 2: 准备恢复环境

```bash
# 2.1 通知所有用户即将进行恢复操作
echo "⚠️  数据库将在 5 分钟后进入维护模式"

# 2.2 停止所有应用连接
kubectl scale deployment -n dev youngth-guard-backend --replicas=0
kubectl scale deployment -n prod youngth-guard-backend --replicas=0
# 对所有使用该数据库的应用执行相同操作

# 2.3 验证没有活动连接
kubectl -n infra exec postgres-0 -- psql -U postgres -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname NOT IN ('postgres', 'template0', 'template1');"

# 2.4 停止 Postgres
kubectl -n infra scale statefulset postgres --replicas=0

# 2.5 等待 Pod 完全停止
kubectl -n infra wait --for=delete pod/postgres-0 --timeout=120s
```

---

### Step 3: 执行 PITR 恢复

```bash
# 3.1 创建恢复 Job（使用模板）
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-restore-$(date +%Y%m%d-%H%M%S)
  namespace: infra
  labels:
    app: postgres
    component: restore
    managed-by: manual
spec:
  template:
    metadata:
      labels:
        app: postgres
        component: restore
    spec:
      restartPolicy: Never
      containers:
        - name: restore
          image: pgbackrest/pgbackrest:latest
          command:
            - /bin/bash
            - -c
            - |
              set -e
              echo "Starting PITR to 2025-12-18 10:30:00"

              pgbackrest --stanza=postgres \
                --type=time \
                --target="2025-12-18 10:30:00+00" \
                --delta \
                restore

              echo "Restore completed"
          env:
            - name: PGBACKREST_CONFIG
              value: /etc/pgbackrest/pgbackrest.conf
          volumeMounts:
            - name: pgbackrest-config
              mountPath: /etc/pgbackrest
              readOnly: true
            - name: pgbackrest-repo
              mountPath: /pgbackrest/repo
              readOnly: true
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
      volumes:
        - name: pgbackrest-config
          configMap:
            name: pgbackrest-config
        - name: pgbackrest-repo
          persistentVolumeClaim:
            claimName: pgbackrest-repo
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-data-postgres-0
EOF

# 3.2 监控恢复进度
kubectl -n infra logs -f job/postgres-restore-TIMESTAMP

# 3.3 等待恢复完成
kubectl -n infra wait --for=condition=complete job/postgres-restore-TIMESTAMP --timeout=1800s
```

---

### Step 4: 启动 Postgres 并验证

```bash
# 4.1 启动 Postgres
kubectl -n infra scale statefulset postgres --replicas=1

# 4.2 等待 Pod 就绪
kubectl -n infra wait --for=condition=ready pod/postgres-0 --timeout=300s

# 4.3 检查 Postgres 日志
kubectl -n infra logs postgres-0 --tail=50

# 4.4 验证恢复时间点
kubectl -n infra exec postgres-0 -- psql -U postgres -c \
  "SELECT pg_last_wal_replay_lsn(), pg_last_xact_replay_timestamp();"

# 4.5 验证数据完整性
# 检查关键表的数据
kubectl -n infra exec postgres-0 -- psql -U postgres -d your_database -c \
  "SELECT count(*) FROM important_table;"

# 4.6 检查最后的事务时间
kubectl -n infra exec postgres-0 -- psql -U postgres -d your_database -c \
  "SELECT max(updated_at) FROM important_table;"
```

---

### Step 5: 恢复应用服务

```bash
# 5.1 逐步恢复应用（先 dev，验证后再 prod）
kubectl scale deployment -n dev youngth-guard-backend --replicas=2

# 5.2 验证应用连接
kubectl -n dev logs -f deployment/youngth-guard-backend

# 5.3 测试应用功能
curl http://youngth-guard-backend.dev.svc.cluster.local:8000/health

# 5.4 确认无误后恢复生产环境
kubectl scale deployment -n prod youngth-guard-backend --replicas=3

# 5.5 通知用户服务已恢复
echo "✅ 数据库已恢复到 2025-12-18 10:30:00"
```

---

## 🔍 验证备份可恢复性（定期演练）

### 每月演练 Checklist

**目标：** 确保备份真的可以用于恢复

```bash
# 1. 在测试环境创建恢复演练
kubectl create namespace postgres-test

# 2. 恢复最新备份到测试环境
# (使用独立的 PVC，不影响生产)

# 3. 验证数据完整性
# - 检查关键表的行数
# - 验证数据一致性
# - 测试应用连接

# 4. 记录演练结果
# - 恢复耗时
# - 发现的问题
# - 改进措施

# 5. 清理测试环境
kubectl delete namespace postgres-test
```

---

## 📊 监控备份状态

### 关键指标

```bash
# 1. 最近备份时间
kubectl -n infra exec postgres-0 -- \
  pgbackrest --stanza=postgres info --output=json | jq '.[] | .backup[] | .timestamp'

# 2. 备份大小趋势
kubectl -n infra exec postgres-0 -- \
  pgbackrest --stanza=postgres info --output=json | jq '.[] | .backup[] | .info.size'

# 3. WAL 归档延迟
kubectl -n infra exec postgres-0 -- psql -U postgres -c \
  "SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()));"

# 4. 备份仓库磁盘使用
kubectl -n infra exec postgres-0 -- df -h /pgbackrest/repo
```

### 告警规则

建议配置以下告警：
- ✅ 备份失败超过 2 次
- ✅ 最近 48 小时没有成功备份
- ✅ WAL 归档延迟超过 1 小时
- ✅ 备份仓库磁盘使用超过 80%

---

## ⚠️ 常见问题与解决

### Q1: 恢复时报错 "backup info missing"

**原因：** 备份仓库损坏或未正确初始化

**解决：**
```bash
# 重新创建 stanza
kubectl -n infra exec postgres-0 -- \
  pgbackrest --stanza=postgres stanza-create --force
```

### Q2: WAL 归档堆积

**原因：** 归档进程故障或磁盘满

**解决：**
```bash
# 检查归档状态
kubectl -n infra exec postgres-0 -- psql -U postgres -c \
  "SELECT archived_count, failed_count FROM pg_stat_archiver;"

# 清理旧的 WAL（谨慎！）
kubectl -n infra exec postgres-0 -- \
  find /var/lib/postgresql/wal_archive -name "*.backup" -mtime +7 -delete
```

### Q3: 恢复后应用报错

**原因：** 恢复到的时间点不一致

**解决：**
1. 检查应用期望的数据状态
2. 可能需要重新运行部分数据迁移
3. 验证所有相关数据库的一致性

---

## 📚 进阶：备份到对象存储

**生产环境建议：** 将备份推送到 S3/MinIO

```yaml
# pgbackrest.conf 添加
[global]
repo1-type=s3
repo1-s3-endpoint=s3.amazonaws.com
repo1-s3-bucket=my-postgres-backups
repo1-s3-region=us-east-1
repo1-s3-key=<access-key>
repo1-s3-key-secret=<secret-key>
```

**优势：**
- 异地容灾
- 无限存储
- 自动过期管理
- 版本控制

---

## ✅ Checklist：PITR 操作前

- [ ] 确认目标恢复时间
- [ ] 验证备份覆盖该时间点
- [ ] 通知所有相关人员
- [ ] 停止所有应用连接
- [ ] 备份当前数据（以防万一）
- [ ] 准备回滚计划
- [ ] 文档记录操作步骤
- [ ] 预估恢复时间窗口
