# ljwx-bookstore GitOps 配置

智能小说阅读平台的 Kubernetes GitOps 部署配置，使用 Kustomize 管理。

## 📋 概览

- **应用名称**: ljwx-bookstore
- **代码仓库**: https://github.com/BrunoGaoSZ/ljwx-bookstore
- **GitOps 仓库**: https://github.com/BrunoGaoSZ/ljwx-deploy
- **命名空间**: bookstore
- **配置管理**: Kustomize
- **GitOps 控制器**: Argo CD

## 🚀 快速部署

### 前置条件

1. **Kubernetes 集群**: K3s 或其他 Kubernetes 集群
2. **Argo CD**: 已安装并配置
3. **基础设施**:
   - MySQL 8.0 (infra namespace)
   - Redis 7.2.12 (ljwx-health namespace)
   - Traefik Ingress Controller
   - cert-manager + Let's Encrypt

### 创建必需的 Secrets

```bash
# 1. 创建命名空间
kubectl create namespace bookstore

# 2. GHCR 镜像拉取凭证
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  -n bookstore

# 3. Redis 连接配置
kubectl create secret generic redis-secret \
  --from-literal=host=redis.ljwx-health.svc.cluster.local \
  --from-literal=port=6379 \
  --from-literal=password=<redis-password> \
  -n bookstore
```

### 部署应用

```bash
# 方法 1: 使用 Argo CD Application CRD
kubectl apply -f argocd-apps/40-ljwx-bookstore.yaml

# 方法 2: 使用 Argo CD CLI
argocd app create ljwx-bookstore \
  --repo https://github.com/BrunoGaoSZ/ljwx-deploy.git \
  --path apps/ljwx-bookstore/overlays/bookstore \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace bookstore \
  --sync-policy automated \
  --auto-prune \
  --self-heal

# 查看部署状态
argocd app get ljwx-bookstore
argocd app sync ljwx-bookstore
```

## 📁 目录结构

```
apps/ljwx-bookstore/
├── base/                           # 基础配置
│   ├── deployment.yaml            # Deployment 定义
│   ├── service.yaml               # Service 定义
│   ├── ingress.yaml               # Ingress + Middleware（HTTPS + 根路径重定向）
│   ├── ghcr-secret.yaml           # GHCR 拉取凭证引用
│   ├── redis-secret.yaml          # Redis 连接配置引用
│   └── kustomization.yaml         # Kustomize 基础配置
│
└── overlays/                       # 环境特定配置
    └── bookstore/                  # bookstore 环境
        └── kustomization.yaml      # 镜像版本配置（自动更新）
```

## ⚙️ 配置说明

### Deployment 配置

**文件**: `base/deployment.yaml`

- **副本数**: 2
- **镜像**: `ghcr.io/brunogaosz/ljwx-bookstore/bookstore:bookstore-<commit>`
- **端口**: 8080
- **环境变量**:
  - `SPRING_DATASOURCE_URL`: MySQL 连接（infra namespace）
  - `SPRING_DATASOURCE_USERNAME`: bookstore
  - `SPRING_DATASOURCE_PASSWORD`: 从 mysql-standalone Secret 获取
  - `SPRING_DATA_REDIS_HOST`: 从 redis-secret 获取
  - `SPRING_DATA_REDIS_PORT`: 从 redis-secret 获取
  - `SPRING_DATA_REDIS_PASSWORD`: 从 redis-secret 获取
- **健康检查**:
  - Liveness Probe: `/fiction/actuator/health/liveness`
  - Readiness Probe: `/fiction/actuator/health/readiness`

### Service 配置

**文件**: `base/service.yaml`

- **类型**: ClusterIP
- **端口**: 8080 → 8080

### Ingress 配置

**文件**: `base/ingress.yaml`

- **Ingress Controller**: Traefik
- **域名**: bookstore.lingjingwanxiang.cn
- **功能**:
  - ✅ HTTPS 自动重定向
  - ✅ Let's Encrypt 证书自动签发（cert-manager）
  - ✅ 根路径（`/`）自动重定向到 `/fiction/index`
- **TLS Secret**: bookstore-lingjingwanxiang-tls
- **ClusterIssuer**: dnspod-letsencrypt

**Traefik Middleware**: 实现根路径重定向
```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: redirect-root
  namespace: bookstore
spec:
  redirectRegex:
    regex: "^https?://[^/]+/$"
    replacement: "https://bookstore.lingjingwanxiang.cn/fiction/index"
    permanent: false
```

### Kustomize 配置

**基础配置** (`base/kustomization.yaml`):
```yaml
resources:
  - deployment.yaml
  - service.yaml
  - ingress.yaml
  - ghcr-secret.yaml
  - redis-secret.yaml
```

**环境配置** (`overlays/bookstore/kustomization.yaml`):
```yaml
resources:
  - ../../base

namespace: bookstore

images:
  - name: ghcr.io/brunogaosz/ljwx-bookstore/bookstore
    newName: ghcr.io/brunogaosz/ljwx-bookstore/bookstore
    newTag: "bookstore-<commit-sha>"  # 由 CI 自动更新
```

## 🔄 GitOps 工作流程

### 自动化部署流程

1. **代码提交** → GitHub (ljwx-bookstore)
2. **GitHub Actions CI**:
   - 构建 Docker 镜像（多架构：linux/amd64, linux/arm64）
   - 推送到 GHCR: `ghcr.io/brunogaosz/ljwx-bookstore/bookstore:bookstore-<commit>`
3. **GitOps 更新**:
   - CI 自动创建 PR 到 ljwx-deploy 仓库
   - 更新 `overlays/bookstore/kustomization.yaml` 中的镜像标签
4. **PR 合并** → main 分支
5. **Argo CD 同步**:
   - 检测 Git 仓库变更（轮询间隔：3 分钟）
   - 自动同步到 Kubernetes 集群
6. **滚动更新**:
   - Kubernetes 执行零停机滚动更新
   - 新 Pod 启动 → 健康检查通过 → 旧 Pod 终止

### 手动更新配置

```bash
# 1. 克隆 GitOps 仓库
git clone https://github.com/BrunoGaoSZ/ljwx-deploy.git
cd ljwx-deploy

# 2. 修改配置
vim apps/ljwx-bookstore/base/deployment.yaml

# 3. 提交变更
git add .
git commit -m "feat: update bookstore configuration"
git push

# 4. Argo CD 自动同步（~3 分钟）
# 或手动触发同步
argocd app sync ljwx-bookstore
```

## 📊 监控和验证

### 查看部署状态

```bash
# Argo CD 应用状态
argocd app get ljwx-bookstore

# Kubernetes 资源状态
kubectl get all -n bookstore

# Pod 日志
kubectl logs -f -n bookstore -l app=bookstore

# Ingress 状态
kubectl get ingress -n bookstore
kubectl describe ingress bookstore-ingress -n bookstore
```

### 健康检查

```bash
# 应用健康检查
curl https://bookstore.lingjingwanxiang.cn/fiction/actuator/health

# 预期响应
{
  "status": "UP",
  "components": {
    "db": {"status": "UP"},
    "redis": {"status": "UP"},
    "diskSpace": {"status": "UP"},
    "livenessState": {"status": "UP"},
    "readinessState": {"status": "UP"}
  }
}
```

### 访问测试

```bash
# 测试根路径重定向
curl -I https://bookstore.lingjingwanxiang.cn/
# 预期: HTTP 307 重定向到 /fiction/index

# 访问应用
curl -L https://bookstore.lingjingwanxiang.cn/
# 预期: HTTP 200，返回首页 HTML
```

## 🔧 故障排查

### Pod 无法启动

```bash
# 查看 Pod 状态
kubectl get pods -n bookstore

# 查看 Pod 事件
kubectl describe pod <pod-name> -n bookstore

# 查看日志
kubectl logs <pod-name> -n bookstore

# 常见问题：
# 1. 镜像拉取失败 → 检查 ghcr-secret
# 2. 健康检查失败 → 检查 MySQL/Redis 连接
# 3. ConfigMap/Secret 不存在 → 检查依赖资源
```

### Ingress 无法访问

```bash
# 检查 Ingress 资源
kubectl get ingress -n bookstore
kubectl describe ingress bookstore-ingress -n bookstore

# 检查 TLS 证书
kubectl get certificate -n bookstore
kubectl describe certificate -n bookstore

# 检查 Traefik 日志
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
```

### Argo CD 同步失败

```bash
# 查看同步状态
argocd app get ljwx-bookstore

# 查看同步日志
argocd app logs ljwx-bookstore

# 手动同步
argocd app sync ljwx-bookstore --force

# 常见问题：
# 1. Git 仓库无法访问 → 检查网络和认证
# 2. Kustomize 配置错误 → 检查 YAML 语法
# 3. 资源冲突 → 使用 --force 强制同步
```

## 📖 相关文档

- **代码仓库**: https://github.com/BrunoGaoSZ/ljwx-bookstore
- **应用访问**: https://bookstore.lingjingwanxiang.cn
- **Argo CD 指南**: [docs/argocd-migration/README.md](../../docs/argocd-migration/README.md)
- **Flyway 迁移**: [docs/flyway-guide/README.md](../../docs/flyway-guide/README.md)

## 🎯 最佳实践

1. **永远不要直接修改 Kubernetes 资源** - 所有变更通过 Git 提交
2. **使用语义化提交信息** - 便于追踪变更历史
3. **环境隔离** - 使用 Kustomize overlays 管理不同环境
4. **自动化测试** - CI 流程包含镜像构建和推送验证
5. **监控告警** - 配置 Prometheus + Grafana 监控（计划中）

## 📝 变更历史

- **2025-12-20**: 配置 HTTPS Ingress + 根路径重定向
- **2025-12-19**: 完成 GitOps 自动部署流程
- **2025-12-18**: 配置 MySQL 和 Redis 连接
- **2025-12-17**: 初始化 Kustomize 配置
