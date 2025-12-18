# Infra Postgres Deployment

## 方案选择说明

### 为什么选择 StatefulSet 而不是 Operator？

**选择：StatefulSet**

**理由：**

1. **简单性**
   - 不需要额外安装和维护 Operator（如 Zalando、CrunchyData）
   - 标准 Kubernetes 资源，团队容易理解
   - 符合"不引入新技术栈"原则

2. **足够性**
   - 单实例 Postgres 满足当前需求
   - StatefulSet 提供稳定的网络标识和持久化存储
   - 配合 PITR 备份足以保证数据安全

3. **可维护性**
   - 配置透明，易于调试
   - 升级和回滚流程清晰
   - 出问题时容易定位

**何时考虑 Operator？**
- 需要高可用（主从复制、自动故障转移）
- 需要自动化备份管理
- 团队规模大，需要标准化操作

---

## 架构说明

### 资源配置

**内存分配（2GB）：**
- `shared_buffers`: 512MB（缓存数据）
- `effective_cache_size`: 1536MB（查询优化参考）
- `work_mem`: 2.6MB（排序、哈希操作）
- `maintenance_work_mem`: 128MB（VACUUM、创建索引）

**存储：**
- 数据卷：20GB（实际数据）
- WAL 归档卷：10GB（备份和 PITR）

**连接数：**
- `max_connections`: 200（支持多个应用并发连接）

---

## 部署步骤

### 1. 部署 Postgres

```bash
# 应用所有资源
kubectl apply -k infra/postgres/

# 等待 Pod 就绪
kubectl wait --for=condition=ready pod -l app=postgres -n infra --timeout=300s
```

### 2. 验证部署

```bash
# 检查 Pod 状态
kubectl -n infra get pods -l app=postgres

# 检查 PVC
kubectl -n infra get pvc

# 检查服务
kubectl -n infra get svc postgres-lb

# 测试连接
kubectl -n infra exec -it postgres-0 -- psql -U postgres -c "SELECT version();"
```

### 3. 连接信息

**集群内访问：**
```
Host: postgres-lb.infra.svc.cluster.local
Port: 5432
User: postgres
Password: (from secret postgres-admin)
```

**连接字符串示例：**
```
postgresql://postgres:password@postgres-lb.infra.svc.cluster.local:5432/dbname
```

---

## 安全注意事项

### ⚠️ 生产环境必须修改

1. **修改管理员密码**
   ```bash
   kubectl -n infra create secret generic postgres-admin \
     --from-literal=POSTGRES_USER=postgres \
     --from-literal=POSTGRES_PASSWORD='YourSecurePassword' \
     --from-literal=POSTGRES_HOST=postgres-lb.infra.svc.cluster.local \
     --from-literal=POSTGRES_PORT=5432 \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

2. **限制网络访问**
   - 使用 NetworkPolicy 限制只有应用 namespace 可以访问
   - 不要创建 LoadBalancer 或 NodePort

3. **启用 SSL/TLS**
   - 生产环境配置 SSL 证书
   - 强制客户端使用 SSL 连接

---

## 监控指标

**关键指标：**
- 连接数使用率
- 缓存命中率
- 慢查询数量
- WAL 归档延迟
- 磁盘使用率

**查询当前连接：**
```sql
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
```

---

## 故障排查

### Pod 无法启动

```bash
# 查看日志
kubectl -n infra logs postgres-0

# 查看事件
kubectl -n infra describe pod postgres-0

# 检查 PVC
kubectl -n infra get pvc
kubectl -n infra describe pvc postgres-data-postgres-0
```

### 连接被拒绝

```bash
# 检查服务
kubectl -n infra get svc postgres-lb

# 测试网络
kubectl run -it --rm debug --image=postgres:16-alpine --restart=Never -- \
  psql -h postgres-lb.infra.svc.cluster.local -U postgres
```

### 磁盘空间不足

```bash
# 检查磁盘使用
kubectl -n infra exec postgres-0 -- df -h

# 清理日志（如果需要）
kubectl -n infra exec postgres-0 -- find /var/log/postgresql -name "*.log" -mtime +7 -delete
```

---

## 升级 Postgres 版本

### 小版本升级（16.1 → 16.2）

```bash
# 更新镜像
kubectl -n infra set image statefulset/postgres postgres=postgres:16.2-alpine

# 滚动重启
kubectl -n infra rollout status statefulset/postgres
```

### 大版本升级（16 → 17）

⚠️ **需要 pg_upgrade 或逻辑备份/恢复**

1. 备份数据
2. 创建新 Postgres 17 实例
3. 使用 pg_dump + pg_restore 迁移
4. 验证后切换
5. 删除旧实例

详细步骤见 STEP 8 Playbook。
