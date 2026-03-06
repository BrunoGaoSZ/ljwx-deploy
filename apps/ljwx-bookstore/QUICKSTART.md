# ljwx-bookstore K8s 配置快速参考

## 📋 更新总结 (2026-01-13)

### ✅ 完成的更新

1. **ConfigMap** - 同步最新配置
   - JVM: G1GC → ZGC
   - AI 模型: qwen2.5:7b → lingjingwanxiang:32b
   - OpenTelemetry: gRPC(4317) → HTTP(4318)

2. **ServiceMonitor** - 新增 Prometheus 集成
   - 自动服务发现
   - 指标过滤优化
   - 标签增强

3. **文档** - 完善部署指南
   - DEPLOYMENT_GUIDE.md
   - CHANGELOG.md

### 🚀 快速部署

#### 前置条件检查
```bash
# 1. 检查 Infra 服务
kubectl get svc -n infra mysql-infra redis-infra

# 2. 检查 Ollama 服务
kubectl get svc -n devops ollama

# 3. 检查 OTel Collector
kubectl get svc -n tracing otel-collector-opentelemetry-collector

# 4. 检查 Prometheus Operator
kubectl get crd servicemonitors.monitoring.coreos.com
```

#### 创建 Secret
```bash
# 推荐：在 ljwx-deploy 仓库根目录执行，自动从 infra-credentials 拉取密码
./scripts/create-app-secret.sh ljwx-bookstore /root/codes/.env

# 手动方式（如需逐项指定）：
kubectl create secret generic ljwx-bookstore-secret \
  --namespace=ljwx-bookstore \
  --from-literal=DB_HOST='mysql-infra.infra.svc.cluster.local' \
  --from-literal=DB_PORT='3306' \
  --from-literal=DB_NAME='org_fiction' \
  --from-literal=DB_USER='bookstore' \
  --from-literal=DB_PASSWORD='YOUR_PASSWORD' \
  --from-literal=REDIS_HOST='redis-infra.infra.svc.cluster.local' \
  --from-literal=REDIS_PORT='6379' \
  --from-literal=REDIS_PASSWORD='YOUR_PASSWORD' \
  --from-literal=WX_APP_SECRET='YOUR_SECRET' \
  --from-literal=WX_MCH_KEY='YOUR_KEY' \
  --from-literal=MAIL_PASSWORD='YOUR_PASSWORD' \
  --from-literal=SMS_TENCENT_APPKEY='YOUR_KEY' \
  --from-literal=STORAGE_ALIYUN_ACCESS_KEY_ID='YOUR_KEY_ID' \
  --from-literal=STORAGE_ALIYUN_ACCESS_KEY_SECRET='YOUR_SECRET'
```

如果 `/root/codes/.env` 中存在 Claude 代理配置，也可以单独同步可选的
`ljwx-bookstore-llm-secret`：

```bash
./scripts/sync-llm-secret.sh ljwx-bookstore /root/codes/.env
kubectl rollout restart deployment/ljwx-bookstore -n ljwx-bookstore
```

#### 部署应用
```bash
# 方式 1: Kustomize
cd ~/work/codes/ljwx/ljwx-deploy/apps/ljwx-bookstore/base
kubectl apply -k .

# 方式 2: Argo CD (推荐)
# 提交到 Git，Argo CD 自动同步
```

#### 验证部署
```bash
# 检查 Pod
kubectl get pods -n ljwx-bookstore -w

# 检查日志
kubectl logs -n ljwx-bookstore -l app=ljwx-bookstore -f

# 检查健康状态
kubectl exec -n ljwx-bookstore deployment/ljwx-bookstore -- \
  wget -qO- http://localhost:8844/fiction/actuator/health | jq .

# 检查 ServiceMonitor
kubectl get servicemonitor -n ljwx-bookstore

# 访问应用
curl https://bookstore.lingjingwanxiang.cn/fiction/index
```

### 📊 监控验证

```bash
# 1. 检查 Prometheus Target
# 访问 Prometheus UI，查看 Status > Targets
# 应该看到: ljwx-bookstore/ljwx-bookstore (1/1 up)

# 2. 查询指标
# PromQL 示例:
# - jvm_memory_used_bytes{namespace="ljwx-bookstore"}
# - http_server_requests_seconds_count{namespace="ljwx-bookstore"}
# - hikaricp_connections_active{namespace="ljwx-bookstore"}

# 3. 检查 OTel 追踪
# 访问 Jaeger UI，搜索 service: ljwx-bookstore
```

### 🔧 故障排查

#### Pod 无法启动
```bash
# 查看事件
kubectl describe pod -n ljwx-bookstore -l app=ljwx-bookstore

# 查看 init container 日志
kubectl logs -n ljwx-bookstore -l app=ljwx-bookstore -c wait-for-mysql

# 测试 MySQL 连接
kubectl exec -n ljwx-bookstore deployment/ljwx-bookstore -- \
  nc -zv mysql-infra.infra.svc.cluster.local 3306
```

#### ServiceMonitor 不生效
```bash
# 检查 ServiceMonitor 配置
kubectl get servicemonitor -n ljwx-bookstore ljwx-bookstore -o yaml

# 检查 Prometheus 日志
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus

# 检查 Service 标签
kubectl get svc -n ljwx-bookstore ljwx-bookstore -o yaml | grep -A5 labels
```

#### OTel 连接失败
```bash
# 测试 OTel Collector 连接
kubectl exec -n ljwx-bookstore deployment/ljwx-bookstore -- \
  nc -zv otel-collector-opentelemetry-collector.tracing.svc.cluster.local 4318

# 查看 OTel Collector 日志
kubectl logs -n tracing -l app.kubernetes.io/name=opentelemetry-collector
```

### 📁 文件结构

```
apps/ljwx-bookstore/
├── base/
│   ├── configmap.yaml          # ✅ 已更新 (AI 模型, JVM, OTel)
│   ├── deployment.yaml         # ✅ 已验证
│   ├── service.yaml            # ✅ 已验证
│   ├── ingress.yaml            # ✅ 已验证
│   ├── servicemonitor.yaml     # ✅ 新增
│   ├── namespace.yaml          # ✅ 已验证
│   ├── db-init-job.yaml        # ✅ 已验证
│   ├── kustomization.yaml      # ✅ 已更新
│   ├── DEPLOYMENT_GUIDE.md     # ✅ 新增
│   ├── DNS_SETUP.md            # 已存在
│   └── SECRET_MANAGEMENT.md    # 已存在
├── overlays/
│   └── ljwx-bookstore/
│       └── kustomization.yaml  # 环境特定配置
├── CHANGELOG.md                # ✅ 新增
└── QUICKSTART.md               # 本文件
```

### 🔑 关键配置

#### AI 模型配置
```yaml
AI_LOCAL_DEFAULT_MODEL: "lingjingwanxiang:32b"
AI_LOCAL_FALLBACK_MODEL: "lingjingwanxiang:32b"
AI_LLM_MODEL: "lingjingwanxiang:32b"
AI_LLM_ADVANCED_MODEL: "lingjingwanxiang:32b"
```

#### OpenTelemetry 配置
```yaml
OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector-opentelemetry-collector.tracing.svc.cluster.local:4318"
OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
```

#### 资源配置
```yaml
requests:
  cpu: 250m
  memory: 512Mi
limits:
  cpu: 1000m
  memory: 1Gi
```

### 📚 相关文档

- **详细部署指南**: `base/DEPLOYMENT_GUIDE.md`
- **变更日志**: `CHANGELOG.md`
- **Secret 管理**: `base/SECRET_MANAGEMENT.md`
- **DNS 配置**: `base/DNS_SETUP.md`

### 🔗 相关链接

- **应用仓库**: https://gitea.omniverseai.net/ljwx/ljwx-bookstore
- **部署仓库**: https://gitea.omniverseai.net/ljwx/ljwx-deploy
- **Harbor**: https://harbor.omniverseai.net/harbor/projects/2/repositories/ljwx-bookstore
- **Argo CD**: http://argocd.omniverseai.net
- **Grafana**: http://grafana.monitoring.svc.cluster.local:3000

### ⚠️ 注意事项

1. **Secret 不要提交到 Git**
2. **确保 Ollama 已下载 lingjingwanxiang:32b 模型**
3. **首次部署需要等待 Flyway 迁移完成（约 2-3 分钟）**
4. **ServiceMonitor 需要 Prometheus Operator**
5. **OpenTelemetry 需要 OTel Collector 运行**

### 🆘 获取帮助

- **问题反馈**: https://gitea.omniverseai.net/ljwx/ljwx-deploy/issues
- **联系人**: DevOps Team

---

**最后更新**: 2026-01-13
**版本**: v1.0.0
