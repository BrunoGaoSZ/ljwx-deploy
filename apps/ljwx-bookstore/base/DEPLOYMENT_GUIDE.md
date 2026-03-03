# ljwx-bookstore Kubernetes 部署指南

## 概述

本文档描述如何通过 GitOps (Argo CD) 部署 ljwx-bookstore 到 Kubernetes 集群的 `ljwx-bookstore` namespace。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     ljwx-bookstore                          │
│                    Namespace                                │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  Deployment  │───▶│   Service    │───▶│   Ingress    │ │
│  │   (1 Pod)    │    │  ClusterIP   │    │ book.omni... │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         │                                                   │
│         │ ConfigMap + Secret                               │
│         ▼                                                   │
│  ┌──────────────────────────────────────┐                  │
│  │  ServiceMonitor (Prometheus)         │                  │
│  └──────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ 跨 namespace 访问
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    infra Namespace                          │
│                                                             │
│  ┌──────────────┐              ┌──────────────┐            │
│  │    MySQL     │              │    Redis     │            │
│  │ (org_fiction)│              │  (缓存)      │            │
│  └──────────────┘              └──────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

## 前置条件

### 1. Infra 服务就绪

确保以下服务在 `infra` namespace 中运行：

```bash
# 检查 MySQL
kubectl get svc -n infra mysql-infra

# 检查 Redis
kubectl get svc -n infra redis-infra
```

### 2. 镜像已推送

确保镜像已推送到 Harbor：
```bash
harbor.omniverseai.net/ljwx/ljwx-bookstore:latest
```

### 3. Prometheus Operator 就绪

确保 Prometheus Operator 已安装（用于 ServiceMonitor）：
```bash
kubectl get crd servicemonitors.monitoring.coreos.com
```

### 4. OpenTelemetry Collector 就绪

确保 OTel Collector 在 `tracing` namespace 运行：
```bash
kubectl get svc -n tracing otel-collector-opentelemetry-collector
```

## 部署步骤

### 步骤 1: 创建 Secret

创建包含敏感信息的 Secret（**不要提交到 Git**）：

```bash
kubectl create secret generic ljwx-bookstore-secret \
  --namespace=ljwx-bookstore \
  --from-literal=DB_HOST='mysql-infra.infra.svc.cluster.local' \
  --from-literal=DB_PORT='3306' \
  --from-literal=DB_NAME='org_fiction' \
  --from-literal=DB_USER='bookstore' \
  --from-literal=DB_PASSWORD='YOUR_DB_PASSWORD' \
  --from-literal=REDIS_HOST='redis-infra.infra.svc.cluster.local' \
  --from-literal=REDIS_PORT='6379' \
  --from-literal=REDIS_PASSWORD='YOUR_REDIS_PASSWORD' \
  --from-literal=WX_APP_SECRET='YOUR_WX_APP_SECRET' \
  --from-literal=WX_MCH_KEY='YOUR_WX_MCH_KEY' \
  --from-literal=MAIL_PASSWORD='YOUR_MAIL_PASSWORD' \
  --from-literal=SMS_TENCENT_APPKEY='YOUR_SMS_APPKEY' \
  --from-literal=STORAGE_ALIYUN_ACCESS_KEY_ID='YOUR_ALIYUN_KEY_ID' \
  --from-literal=STORAGE_ALIYUN_ACCESS_KEY_SECRET='YOUR_ALIYUN_KEY_SECRET' \
  --dry-run=client -o yaml | kubectl apply -f -
```

**生产环境建议**：使用 External Secrets Operator 或 Sealed Secrets 管理敏感信息。

### 步骤 2: 部署应用 (GitOps)

#### 方式 A: 使用 Argo CD (推荐)

1. 创建 Argo CD Application：

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ljwx-bookstore
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://gitea.omniverseai.net/ljwx/ljwx-deploy.git
    targetRevision: main
    path: apps/ljwx-bookstore/base
  destination:
    server: https://kubernetes.default.svc
    namespace: ljwx-bookstore
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

2. 应用到集群：

```bash
kubectl apply -f argocd-application.yaml
```

#### 方式 B: 使用 kubectl + Kustomize

```bash
cd apps/ljwx-bookstore/base
kubectl apply -k .
```

### 步骤 3: 验证部署

```bash
# 检查所有资源
kubectl get all -n ljwx-bookstore

# 检查 Pod 状态
kubectl get pods -n ljwx-bookstore -w

# 检查日志
kubectl logs -n ljwx-bookstore -l app=ljwx-bookstore -f

# 检查健康状态
kubectl exec -n ljwx-bookstore -it deployment/ljwx-bookstore -- \
  wget -qO- http://localhost:8844/fiction/actuator/health
```

### 步骤 4: 验证监控

```bash
# 检查 ServiceMonitor
kubectl get servicemonitor -n ljwx-bookstore

# 验证 Prometheus 已发现 Target
# 访问 Prometheus UI: http://prometheus.monitoring.svc.cluster.local:9090
# 查看 Status > Targets，应该看到 ljwx-bookstore/ljwx-bookstore
```

### 步骤 5: 访问应用

```bash
# 获取 Ingress 地址
kubectl get ingress -n ljwx-bookstore

# 访问应用
curl http://book.omniverseai.net/fiction/index
curl http://bookstore.192.168.1.83.nip.io/fiction/index
```

## 配置说明

### 环境变量映射

#### ConfigMap 配置（非敏感）
- `SPRING_PROFILES_ACTIVE`: Spring Profile（prod）
- `JAVA_OPTS`: JVM 参数（使用 ZGC GC）
- `AI_*`: AI 模型配置（lingjingwanxiang:32b）
- `OTEL_*`: OpenTelemetry 追踪配置（HTTP endpoint 4318）
- `MANAGEMENT_*`: Spring Boot Actuator 监控配置

#### Secret 配置（敏感）
- `DB_*`: MySQL 连接信息
- `REDIS_*`: Redis 连接信息
- `WX_*`: 微信支付凭证
- `MAIL_PASSWORD`: 邮件服务密码
- `SMS_*`: 短信服务凭证
- `STORAGE_*`: 对象存储凭证

### 资源配置

```yaml
requests:
  cpu: 250m
  memory: 512Mi
limits:
  cpu: 1000m
  memory: 1Gi
```

### 健康检查

- **Startup Probe**: 初始延迟 30s，最多等待 300s（30次 × 10s）
- **Liveness Probe**: 初始延迟 120s，每 30s 检查一次
- **Readiness Probe**: 初始延迟 60s，每 10s 检查一次

路径：`/fiction/actuator/health`

## 监控指标

### Prometheus 指标端点

```
http://ljwx-bookstore.ljwx-bookstore.svc.cluster.local/fiction/actuator/prometheus
```

### 关键指标

- **JVM 指标**: `jvm_memory_*`, `jvm_gc_*`, `jvm_threads_*`
- **HTTP 指标**: `http_server_requests_*`, `tomcat_*`
- **数据库连接池**: `hikaricp_connections_*`
- **业务指标**: `spring_*`

### Grafana 仪表板

建议导入以下仪表板：
- Spring Boot 2.x Statistics (ID: 11378)
- JVM (Micrometer) (ID: 4701)
- HikariCP Connection Pool (ID: 11976)

## 故障排查

### Pod 启动失败

```bash
# 查看 Pod 事件
kubectl describe pod -n ljwx-bookstore -l app=ljwx-bookstore

# 查看初始化容器日志
kubectl logs -n ljwx-bookstore -l app=ljwx-bookstore -c wait-for-mysql

# 查看应用容器日志
kubectl logs -n ljwx-bookstore -l app=ljwx-bookstore -c ljwx-bookstore
```

### 数据库连接问题

```bash
# 测试从 Pod 到 MySQL 的连接
kubectl exec -n ljwx-bookstore -it deployment/ljwx-bookstore -- \
  nc -zv mysql-infra.infra.svc.cluster.local 3306

# 测试从 Pod 到 Redis 的连接
kubectl exec -n ljwx-bookstore -it deployment/ljwx-bookstore -- \
  nc -zv redis-infra.infra.svc.cluster.local 6379
```

### OpenTelemetry 连接问题

```bash
# 检查 OTel Collector 服务
kubectl get svc -n tracing otel-collector-opentelemetry-collector

# 测试连接
kubectl exec -n ljwx-bookstore -it deployment/ljwx-bookstore -- \
  nc -zv otel-collector-opentelemetry-collector.tracing.svc.cluster.local 4318
```

### ServiceMonitor 不生效

```bash
# 检查 ServiceMonitor 是否被 Prometheus 选中
kubectl get servicemonitor -n ljwx-bookstore ljwx-bookstore -o yaml

# 检查 Prometheus 配置
kubectl get prometheus -n monitoring -o yaml | grep serviceMonitorSelector
```

## 升级和回滚

### 升级镜像

```bash
# 通过 Kustomize 更新镜像标签
cd apps/ljwx-bookstore/base
kustomize edit set image harbor.omniverseai.net/ljwx/ljwx-bookstore:v1.2.0
git commit -am "Update ljwx-bookstore to v1.2.0"
git push

# Argo CD 会自动同步
```

### 手动回滚

```bash
# 查看历史版本
kubectl rollout history deployment/ljwx-bookstore -n ljwx-bookstore

# 回滚到上一个版本
kubectl rollout undo deployment/ljwx-bookstore -n ljwx-bookstore

# 回滚到特定版本
kubectl rollout undo deployment/ljwx-bookstore -n ljwx-bookstore --to-revision=2
```

## 安全建议

1. **不要将 Secret 提交到 Git**
2. 使用 **Network Policies** 限制跨 namespace 访问
3. 启用 **Pod Security Standards** (restricted)
4. 配置 **Resource Quotas** 和 **Limit Ranges**
5. 使用 **External Secrets Operator** 管理敏感信息
6. 启用 **Audit Logging** 记录敏感操作

## 相关链接

- 应用仓库: https://gitea.omniverseai.net/ljwx/ljwx-bookstore
- 部署仓库: https://gitea.omniverseai.net/ljwx/ljwx-deploy
- Harbor 镜像: https://harbor.omniverseai.net/harbor/projects/2/repositories/ljwx-bookstore
- Argo CD: http://argocd.omniverseai.net
- Grafana: http://grafana.monitoring.svc.cluster.local:3000
