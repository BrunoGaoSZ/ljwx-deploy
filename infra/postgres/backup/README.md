# PostgreSQL 备份和恢复

## 📋 概述

本目录包含 PostgreSQL 数据库的自动化备份和恢复配置。

**备份方案：** 使用 `pg_dump` 和 `pg_dumpall` 进行逻辑备份
**镜像：** `postgres:16-alpine`（官方镜像，无需额外依赖）
**存储：** PVC `pgbackrest-repo`（50GB）

---

## 🔄 自动备份策略

### 1. 完整备份（Full Backup）

- **频率：** 每天凌晨 2 点
- **工具：** `pg_dumpall`
- **范围：** 所有数据库（包括角色、权限）
- **保留期：** 7 天
- **文件格式：** `postgres_full_YYYYMMDD_HHMMSS.sql.gz`

### 2. 增量备份（Incremental Backup）

- **频率：** 每 6 小时
- **工具：** `pg_dump`（每个数据库单独备份）
- **范围：** 所有用户数据库
- **保留期：** 2 天
- **文件格式：** `<database>_YYYYMMDD_HHMMSS.sql.gz`

---

## 🧪 手动触发备份

```bash
# 触发完整备份
kubectl -n infra create job --from=cronjob/postgres-backup-full manual-backup-$(date +%Y%m%d%H%M%S)

# 触发增量备份
kubectl -n infra create job --from=cronjob/postgres-backup-incremental manual-backup-$(date +%Y%m%d%H%M%S)
```

---

## 🔙 数据恢复

详细恢复流程请参考 `restore-job-template.yaml` 和 `docs/db-migration-playbook.md`

---

## 📊 查看备份文件

```bash
kubectl -n infra run backup-list --image=postgres:16-alpine --rm -it --restart=Never \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "list",
        "image": "postgres:16-alpine",
        "command": ["ls", "-lh", "/backup/"],
        "volumeMounts": [{"name": "backup", "mountPath": "/backup"}]
      }],
      "volumes": [{"name": "backup", "persistentVolumeClaim": {"claimName": "pgbackrest-repo"}}]
    }
  }'
```
