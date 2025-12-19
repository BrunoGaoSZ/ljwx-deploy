# ljwx-bookstore GitOps 配置

智能小说阅读平台的 GitOps 部署配置。

## 架构

- **代码仓库**: https://github.com/BrunoGaoSZ/ljwx-bookstore
- **Helm Chart**: `ljwx-bookstore/helm/`
- **命名空间**: `bookstore`

## 部署

```bash
# 1. 应用 AppProject（如果未创建）
kubectl apply -f argocd-apps/projects/ljwx-project.yaml

# 2. 部署 bookstore
kubectl apply -f argocd-apps/40-ljwx-bookstore.yaml

# 3. 查看状态
argocd app get ljwx-bookstore
argocd app sync ljwx-bookstore
```

## 配置说明

### 环境配置
- `base/values-common.yaml`: 通用配置
- `overlays/bookstore/values.yaml`: bookstore 环境配置

### 关键配置
- **副本数**: 2
- **镜像**: ghcr.io/brunogaosz/ljwx-bookstore/bookstore:main-latest
- **端口**: 8080
- **Ingress**: bookstore.example.com

## 更新部署

```bash
# 修改配置
vim apps/ljwx-bookstore/overlays/bookstore/values.yaml

# 提交变更
git commit -m "update bookstore config"
git push

# Argo CD 自动同步（~30秒）
```

## 依赖服务

需要创建以下 Secrets：

```bash
kubectl create namespace bookstore

# 数据库凭证（如使用 infra postgres）
kubectl create secret generic bookstore-db-credentials \
  --from-literal=username=bookstore_user \
  --from-literal=password=<password> \
  -n bookstore

# Redis 凭证（如果需要）
kubectl create secret generic bookstore-redis-credentials \
  --from-literal=password=<password> \
  -n bookstore
```

## 相关文档

- **代码仓库**: https://github.com/BrunoGaoSZ/ljwx-bookstore
- **Helm Chart**: ljwx-bookstore/helm/
- **GitOps 仓库**: https://github.com/BrunoGaoSZ/ljwx-deploy
