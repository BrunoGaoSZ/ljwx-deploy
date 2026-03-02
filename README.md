# ljwx-deploy

GitOps 配置仓库，使用 ArgoCD 管理 Kubernetes 集群。

## Bid-MVP Factory Control Plane

- 运行验证：`bash scripts/verify.sh`
- Harbor 复制：`docs/harbor-replication-ghcr.md`
- Promoter/Argo/Smoke 运维：`docs/ops-runbook.md`
- 服务仓 enqueue 工作流片段：`docs/service-repo-workflow-snippet.md`
- Argo dev 自动同步说明：`docs/argocd-dev-autosync.md`

## 目录结构

- `infra/` - 基础设施组件（Gitea Runner 等）
- `argocd-apps/` - ArgoCD Application 定义
- `apps/` - 应用配置
- `cluster/` - 集群级别配置

## 组件

### Gitea Runner (act_runner)

- 支持 Gitea Actions 的弹性 runner
- 自动伸缩: min 1, max 5 (基于 CPU/Memory)
- 支持 Docker build/push
- Harbor registry: https://harbor.omniverseai.net

#### 配置说明

Runner labels:
- `ubuntu-latest` - Ubuntu 22.04 环境
- `ubuntu-22.04` - 明确指定版本
- `docker` - 支持 Docker 操作
- `self-hosted` - 自托管标识

弹性伸缩策略:
- 最小副本: 1
- 最大副本: 5
- CPU 阈值: 70%
- Memory 阈值: 80%
- 扩容: 30秒内最多翻倍或增加2个
- 缩容: 5分钟稳定期，每分钟最多减少50%

## 使用方法

### 1. 获取 Gitea Runner Token

在 Gitea 管理界面：
1. 访问: http://192.168.1.83:33000/admin/actions/runners
2. 点击"创建新的 Runner"
3. 复制生成的 Registration Token

### 2. 创建 Runner Token Secret

```bash
kubectl -n gitea-runner create secret generic runner-token \
  --from-literal=token=YOUR_REGISTRATION_TOKEN
```

### 3. 部署 Runner

ArgoCD 会自动同步并部署 runner。

### 4. 在仓库中使用

创建 `.gitea/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest  # 或 docker, self-hosted
    
    steps:
      - uses: actions/checkout@v4
      
      - name: 构建镜像
        run: |
          docker build -t myapp:${{ gitea.sha }} .
          docker push harbor.omniverseai.net/myproject/myapp:${{ gitea.sha }}
```

## 监控

```bash
# 查看 runner pods
kubectl -n gitea-runner get pods -w

# 查看 HPA 状态
kubectl -n gitea-runner get hpa

# 查看 runner 日志
kubectl -n gitea-runner logs -l app=gitea-runner -f
```

## 故障排查

### Runner 未注册

检查 token 是否正确:
```bash
kubectl -n gitea-runner get secret runner-token -o jsonpath='{.data.token}' | base64 -d
```

### Runner 无法连接 Gitea

检查网络连通性:
```bash
kubectl -n gitea-runner run test --rm -it --image=curlimages/curl -- \
  curl http://192.168.1.83:33000
```

### Docker 权限问题

Runner 使用宿主机 Docker socket，确保有权限访问。
# Test stability
