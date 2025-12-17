# ljwx-deploy

GitOps 配置仓库，使用 ArgoCD 管理 Kubernetes 集群。

## 目录结构

- `infra/` - 基础设施组件（ARC 等）
- `argocd-apps/` - ArgoCD Application 定义
- `apps/` - 应用配置
- `cluster/` - 集群级别配置

## 组件

### ARC (Actions Runner Controller)

- 支持 Gitea Actions 的弹性 runner
- 自动伸缩: min 1, max 5
- 支持 Docker build/push
- Harbor registry: https://harbor.omniverseai.net
