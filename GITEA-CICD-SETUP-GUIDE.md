# Gitea CI/CD 快速配置指南

## 📋 适用场景

为新项目快速配置基于 Gitea Actions + Argo CD 的完整 GitOps 工作流。

## ✅ 前置条件

### 1. 基础设施检查

```bash
# 检查 Gitea Actions Runner
ls -la /Users/brunogao/gitea-runners/runner3/.runner
# 应显示: labels: ["macos:docker:host"] 或 ["docker-builder"]

# 检查 Harbor Registry
docker login harbor.omniverseai.net
# 应成功登录

# 检查 Argo CD
kubectl get application -n argocd
# 应看到 apps-bootstrap 和其他应用
```

### 2. 准备信息

- **项目名称**: 如 `my-app`
- **Gitea 仓库**: `http://192.168.1.83:33000/gao/my-app`
- **Harbor 镜像**: `harbor.omniverseai.net/ljwx/my-app`
- **K8s Namespace**: `my-app-dev` (推荐独立 namespace)
- **Gitea Token**: 从 Gitea 设置 → 应用 → 访问令牌生成

## 🚀 配置步骤

### Step 1: 项目仓库配置 Gitea Workflow

#### 1.1 创建 Workflow 文件

在项目根目录创建 `.gitea/workflows/ci.yaml`:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: harbor.omniverseai.net
  IMAGE_NAME: ljwx/my-app  # 修改为你的项目名

jobs:
  # ==================== Job 1: Lint & Test ====================
  lint-test:
    runs-on: ubuntu-latest  # K8s runner，快速
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci --legacy-peer-deps

      - name: Run linter
        run: npm run lint

      - name: Type check
        run: npm run build:check || npm run build

  # ==================== Job 2: Build & Push ====================
  build-push:
    needs: lint-test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: docker-builder  # 宿主机 runner，有完整 Docker 环境
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Extract metadata
        id: meta
        run: |
          SHORT_SHA=$(echo ${{ github.sha }} | cut -c1-7)
          echo "tag=main-${SHORT_SHA}" >> $GITHUB_OUTPUT
          echo "short_sha=${SHORT_SHA}" >> $GITHUB_OUTPUT

      - name: Log in to Harbor
        run: echo "${{ secrets.HARBOR_PASSWORD }}" | docker login ${{ env.REGISTRY }} -u "${{ secrets.HARBOR_USERNAME }}" --password-stdin

      - name: Set up Docker Buildx
        run: |
          docker buildx create --name ci-builder --use --driver docker-container || docker buildx use ci-builder
          docker buildx inspect --bootstrap

      - name: Build and push Docker image
        run: |
          docker buildx build \
            --platform linux/amd64,linux/arm64 \
            --tag ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.meta.outputs.tag }} \
            --tag ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest \
            --push \
            --progress plain \
            .

      - name: Image digest
        run: |
          docker buildx imagetools inspect ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.meta.outputs.tag }}

  # ==================== Job 3: Update Deploy Repo ====================
  update-deploy:
    needs: build-push
    runs-on: ubuntu-latest
    env:
      IMAGE_TAG: main-${{ github.sha }}
    steps:
      - name: Checkout code
        run: |
          SHORT_SHA=$(echo ${{ github.sha }} | cut -c1-7)
          echo "IMAGE_TAG=main-${SHORT_SHA}" >> $GITHUB_ENV

      - name: Verify tools
        run: |
          node --version
          npm --version
          git --version
          yq --version

      - name: Update deployment repository
        run: |
          # 克隆 ljwx-deploy 仓库 (使用 token 认证)
          git clone http://gao:${{ secrets.DEPLOY_REPO_TOKEN }}@192.168.1.83:33000/gao/ljwx-deploy.git /tmp/ljwx-deploy
          cd /tmp/ljwx-deploy

          # 配置 git
          git config user.name "Gitea Actions"
          git config user.email "actions@gitea.local"

          # 导航到 overlay 目录（修改为你的项目路径）
          cd apps/my-app/overlays/my-app-dev

          # 更新镜像 tag
          yq eval ".images[0].newTag = \"${IMAGE_TAG}\"" -i kustomization.yaml

          # 提交并推送
          git add kustomization.yaml
          git commit -m "chore: update my-app to ${IMAGE_TAG}"
          git push origin main

  # ==================== Job 4: Build PR (仅验证) ====================
  build-pr:
    needs: lint-test
    if: github.event_name == 'pull_request'
    runs-on: docker-builder
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        run: |
          docker buildx create --name ci-builder --use --driver docker-container || docker buildx use ci-builder
          docker buildx inspect --bootstrap

      - name: Build Docker image (no push)
        run: |
          docker buildx build \
            --platform linux/amd64,linux/arm64 \
            --progress plain \
            .
```

#### 1.2 配置 Gitea Secrets

**推荐方式: 使用 Organization Secrets (一次配置，所有项目共享)**

详细配置步骤请参考: **[GITEA-SECRETS-SETUP.md](GITEA-SECRETS-SETUP.md)**

```bash
# Organization 级别配置 (推荐):
# http://192.168.1.83:33000/gao/settings/secrets
# 添加以下 3 个 Secrets，所有项目自动可用:
# - HARBOR_USERNAME: Harbor 用户名
# - HARBOR_PASSWORD: Harbor 密码
# - DEPLOY_REPO_TOKEN: Gitea 访问令牌 (用于更新 ljwx-deploy 仓库)

# 或者项目级别配置 (不推荐):
# http://192.168.1.83:33000/gao/my-app/settings/secrets
# 需要为每个项目单独配置
```

> 💡 **提示**: 如果已经配置了 Organization Secrets，可以跳过此步骤

#### 1.3 确保 Dockerfile 存在

在项目根目录创建 `Dockerfile.prod` (或 `Dockerfile`):

```dockerfile
# 第一阶段：构建
FROM harbor.omniverseai.net/library/node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY . .
RUN npm run build

# 第二阶段：生产
FROM harbor.omniverseai.net/library/nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
```

### Step 2: ljwx-deploy 仓库配置

#### 2.1 创建 Namespace 配置

```bash
cd /path/to/ljwx-deploy

# 创建 namespace 配置文件
cat > cluster/namespace-my-app-dev.yaml <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: my-app-dev
  labels:
    name: my-app-dev
    environment: dev
    app: my-app
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: my-app-quota
  namespace: my-app-dev
spec:
  hard:
    requests.cpu: "500m"
    requests.memory: "512Mi"
    limits.cpu: "1"
    limits.memory: "1Gi"
    persistentvolumeclaims: "5"
    services: "5"
    pods: "10"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: my-app-limits
  namespace: my-app-dev
spec:
  limits:
  - max:
      cpu: "500m"
      memory: "512Mi"
    min:
      cpu: "10m"
      memory: "32Mi"
    default:
      cpu: "100m"
      memory: "128Mi"
    defaultRequest:
      cpu: "50m"
      memory: "64Mi"
    type: Container
EOF

# 更新 cluster/kustomization.yaml
yq eval '.resources += ["namespace-my-app-dev.yaml"]' -i cluster/kustomization.yaml
```

#### 2.2 创建应用部署配置

```bash
# 创建目录结构
mkdir -p apps/my-app/{base,overlays/my-app-dev}

# 创建 base/deployment.yaml
cat > apps/my-app/base/deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  labels:
    app: my-app
    component: web
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
        component: web
    spec:
      containers:
        - name: my-app
          image: harbor.omniverseai.net/ljwx/my-app:latest
          ports:
            - name: http
              containerPort: 80
          livenessProbe:
            httpGet:
              path: /health
              port: 80
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              memory: "64Mi"
              cpu: "25m"
            limits:
              memory: "128Mi"
              cpu: "100m"
EOF

# 创建 base/service.yaml
cat > apps/my-app/base/service.yaml <<EOF
apiVersion: v1
kind: Service
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app: my-app
EOF

# 创建 base/kustomization.yaml
cat > apps/my-app/base/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
EOF

# 创建 overlays/my-app-dev/kustomization.yaml
cat > apps/my-app/overlays/my-app-dev/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-app-dev

resources:
  - ../../base

images:
  - name: harbor.omniverseai.net/ljwx/my-app
    newTag: "latest"  # CI 会自动更新这个 tag

replicas:
  - name: my-app
    count: 1  # dev 环境使用 1 个副本
EOF
```

#### 2.3 创建 Argo CD Application

```bash
# 创建 Application 配置
cat > argocd-apps/60-my-app-dev.yaml <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: http://192.168.1.83:33000/gao/ljwx-deploy.git
    targetRevision: main
    path: apps/my-app/overlays/my-app-dev
  destination:
    server: https://kubernetes.default.svc
    namespace: my-app-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
EOF
```

#### 2.4 提交到 Git

```bash
cd /path/to/ljwx-deploy

# 提交所有变更
git add .
git commit -m "feat: add my-app deployment configuration"
git push origin main

# 等待 30 秒让 apps-bootstrap 自动创建 Application
sleep 30
```

### Step 3: 验证部署

#### 3.1 验证 Argo CD Application

```bash
# 检查 Application 是否自动创建
kubectl get application my-app-dev -n argocd

# 应该显示:
# NAME          SYNC STATUS   HEALTH STATUS
# my-app-dev    Synced        Healthy
```

#### 3.2 验证 Namespace 和资源

```bash
# 检查 namespace
kubectl get namespace my-app-dev

# 检查资源配额
kubectl get resourcequota,limitrange -n my-app-dev

# 检查部署状态
kubectl get all -n my-app-dev
```

#### 3.3 测试完整 CI/CD 流程

```bash
# 在项目仓库中做一个测试提交
cd /path/to/my-app
echo "# Test CI/CD" >> README.md
git add README.md
git commit -m "test: verify CI/CD pipeline"
git push origin main

# 观察流程:
# 1. Gitea Actions 开始构建 (约 3-5 分钟)
# 2. 镜像推送到 Harbor
# 3. ljwx-deploy 仓库自动更新
# 4. Argo CD 检测到变更并同步 (约 30 秒)
# 5. 新 Pod 启动

# 检查 Gitea Actions
# http://192.168.1.83:33000/gao/my-app/actions

# 检查 ljwx-deploy 最新提交
cd /path/to/ljwx-deploy
git pull origin main
git log -1 --oneline
# 应该看到: chore: update my-app to main-xxxxxxx

# 检查 Pod 镜像更新
kubectl describe pod -n my-app-dev -l app=my-app | grep Image:
```

## 🎯 关键配置点

### 1. Runner 选择

```yaml
# 轻量级任务 (lint, test) → K8s runner
runs-on: ubuntu-latest

# Docker 构建任务 → 宿主机 runner
runs-on: docker-builder  # 或 macos
```

### 2. Multi-arch 构建

```yaml
# 必须使用 buildx + atomic push
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --push \  # 一步完成 build + push
  .
```

### 3. Kustomize 路径

```yaml
# CI workflow 中的路径要匹配
cd apps/my-app/overlays/my-app-dev

# Argo CD Application 中的路径
path: apps/my-app/overlays/my-app-dev
```

### 4. Namespace 独立性

```yaml
# 推荐: 每个应用独立 namespace
namespace: my-app-dev

# 而不是: 共享 namespace
namespace: dev  # ❌ 避免
```

## 🔧 常见问题排查

### 问题 1: Build & Push 失败

**症状**: Docker build 失败或推送失败

**检查**:
```bash
# 1. 检查 runner 标签
cat /Users/brunogao/gitea-runners/runner3/.runner

# 2. 检查 Harbor 凭据
echo "$HARBOR_PASSWORD" | docker login harbor.omniverseai.net -u "$HARBOR_USERNAME" --password-stdin

# 3. 检查 buildx builder
docker buildx ls
```

**解决**: 使用 `docker-builder` 标签的 runner，确保 buildx 正确设置

### 问题 2: Update Deploy Repo 不执行

**症状**: Job 显示成功但 ljwx-deploy 未更新

**检查**:
```bash
# 1. 验证 DEPLOY_REPO_TOKEN
# Gitea → 设置 → 应用 → 访问令牌

# 2. 检查路径是否正确
ls -la ljwx-deploy/apps/my-app/overlays/my-app-dev/kustomization.yaml

# 3. 测试 git clone
git clone http://gao:YOUR_TOKEN@192.168.1.83:33000/gao/ljwx-deploy.git /tmp/test
```

**解决**:
- 确保 token 有 `repo` 权限
- 确保路径 `apps/my-app/overlays/my-app-dev` 存在

### 问题 3: Argo CD 不自动同步

**症状**: ljwx-deploy 更新了但 K8s 未部署

**检查**:
```bash
# 1. 检查 Application 状态
kubectl describe application my-app-dev -n argocd

# 2. 检查 apps-bootstrap
kubectl get application apps-bootstrap -n argocd

# 3. 手动触发同步
kubectl patch application my-app-dev -n argocd \
  --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'
```

**解决**:
- 确保 Application 文件名匹配 `*-dev.yaml` 模式
- 等待 3 分钟（Argo CD 默认同步间隔）

### 问题 4: Pod CrashLoopBackOff

**症状**: Pod 启动失败

**检查**:
```bash
# 1. 查看 Pod 日志
kubectl logs -n my-app-dev -l app=my-app --tail=50

# 2. 查看 Pod 事件
kubectl describe pod -n my-app-dev -l app=my-app

# 3. 检查资源限制
kubectl get limitrange -n my-app-dev -o yaml
```

**解决**:
- 确保 Dockerfile 正确配置
- 确保 `/health` 端点存在
- 调整 resources.requests 满足 LimitRange

## 📚 参考文档

- **ljwx-website 成功案例**: `.gitea/workflows/ci.yaml`
- **Gitea Actions 文档**: https://docs.gitea.com/usage/actions/overview
- **Argo CD App of Apps**: `ARGOCD-APP-MANAGEMENT.md`
- **Namespace 策略**: `NAMESPACE-STRATEGY.md`
- **GitOps 原则**: `PROMPT_BLUEPRINT_V2.md`

## 🎉 总结

完成上述步骤后，你的项目将拥有:

✅ 完整的 CI/CD 自动化流程
✅ Multi-arch Docker 镜像
✅ GitOps 声明式部署
✅ 独立的 Namespace 资源隔离
✅ Argo CD 自动同步
✅ 零手动 kubectl 操作

**记住**: Git commit 即部署，完全自动化！🚀
