# Gitea CI/CD 快速参考卡片

## 🎯 一次性配置 (只需做一次)

### 1. Organization Secrets 配置

```bash
# 访问组织设置
http://192.168.1.83:33000/gao/settings/secrets

# 添加 3 个 Secrets:
HARBOR_USERNAME = admin
HARBOR_PASSWORD = [Harbor 密码]
DEPLOY_REPO_TOKEN = [Gitea Token]
```

**详细步骤**: [GITEA-SECRETS-SETUP.md](GITEA-SECRETS-SETUP.md)

### 2. 生成 DEPLOY_REPO_TOKEN

```bash
# 访问个人设置
http://192.168.1.83:33000/user/settings/applications

# 生成新 Token:
Name: gitea-actions-deploy
Scopes: repo, write:repository
```

---

## 📦 为新项目添加 CI/CD (5 分钟)

### Step 1: 复制 Workflow 文件

```bash
cd /path/to/new-project

# 从 ljwx-website 复制模板
curl -o .gitea/workflows/ci.yaml \
  http://192.168.1.83:33000/gao/ljwx-website/raw/branch/main/.gitea/workflows/ci.yaml
```

### Step 2: 修改项目名称

```bash
# 替换镜像名称 (只需修改这一处)
sed -i 's/ljwx\/ljwx-website/ljwx\/my-app/g' .gitea/workflows/ci.yaml

# 或手动修改:
vim .gitea/workflows/ci.yaml
# 找到: IMAGE_NAME: ljwx/ljwx-website
# 改为: IMAGE_NAME: ljwx/my-app
```

### Step 3: 提交并推送

```bash
git add .gitea/workflows/ci.yaml
git commit -m "ci: add Gitea Actions workflow"
git push origin main

# ✅ CI 自动运行，无需配置 Secrets！
```

---

## 🚀 为新项目添加 CD (10 分钟)

### Step 1: 创建 Namespace 配置

```bash
cd /path/to/ljwx-deploy

# 复制模板并修改
cp cluster/namespace-ljwx-website-dev.yaml cluster/namespace-my-app-dev.yaml

# 替换所有 ljwx-website → my-app
sed -i 's/ljwx-website/my-app/g' cluster/namespace-my-app-dev.yaml

# 更新 cluster/kustomization.yaml
yq eval '.resources += ["namespace-my-app-dev.yaml"]' -i cluster/kustomization.yaml
```

### Step 2: 创建应用配置

```bash
# 复制模板
cp -r apps/ljwx-website apps/my-app

# 更新配置
sed -i 's/ljwx-website/my-app/g' apps/my-app/base/*.yaml
sed -i 's/ljwx-website/my-app/g' apps/my-app/overlays/ljwx-website-dev/kustomization.yaml

# 重命名 overlay
mv apps/my-app/overlays/ljwx-website-dev apps/my-app/overlays/my-app-dev

# 更新 namespace
sed -i 's/namespace: ljwx-website-dev/namespace: my-app-dev/' \
  apps/my-app/overlays/my-app-dev/kustomization.yaml
```

### Step 3: 创建 Argo CD Application

```bash
# 复制模板
cp argocd-apps/60-ljwx-website-dev.yaml argocd-apps/60-my-app-dev.yaml

# 替换内容
sed -i 's/ljwx-website/my-app/g' argocd-apps/60-my-app-dev.yaml
```

### Step 4: 提交并推送

```bash
git add .
git commit -m "feat: add my-app deployment configuration"
git push origin main

# 等待 30 秒
sleep 30

# ✅ Argo CD 自动创建 Application 并部署！
kubectl get application my-app-dev -n argocd
```

---

## 📋 完整文档索引

| 文档 | 用途 | 场景 |
|------|------|------|
| **[GITEA-SECRETS-SETUP.md](GITEA-SECRETS-SETUP.md)** | Organization Secrets 配置 | 首次设置 |
| **[GITEA-CICD-SETUP-GUIDE.md](GITEA-CICD-SETUP-GUIDE.md)** | 完整 CI/CD 配置指南 | 新项目配置 |
| **[ARGOCD-APP-MANAGEMENT.md](ARGOCD-APP-MANAGEMENT.md)** | Argo CD App of Apps 使用 | CD 管理 |
| **[NAMESPACE-STRATEGY.md](NAMESPACE-STRATEGY.md)** | Namespace 策略分析 | 架构设计 |
| **[QUICK-REFERENCE.md](QUICK-REFERENCE.md)** | 快速参考卡片 | 日常查阅 |

---

## 🔍 常用命令速查

### CI/CD 调试

```bash
# 查看 Gitea Actions 运行
http://192.168.1.83:33000/gao/[project]/actions

# 查看 Argo CD 应用状态
kubectl get application -n argocd

# 查看 Pod 状态
kubectl get pods -n [namespace] -l app=[app-name]

# 查看 Pod 日志
kubectl logs -n [namespace] -l app=[app-name] --tail=50

# 手动触发 Argo CD 同步
kubectl patch application [app-name] -n argocd \
  --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'
```

### 资源检查

```bash
# 查看 namespace 资源配额使用情况
kubectl get resourcequota -n [namespace]
kubectl describe resourcequota -n [namespace]

# 查看 Pod 资源使用
kubectl top pods -n [namespace]

# 查看 Node 资源使用
kubectl top nodes
```

### Harbor 镜像管理

```bash
# 登录 Harbor
docker login harbor.omniverseai.net

# 查看镜像列表
curl -u admin:password \
  http://harbor.omniverseai.net/api/v2.0/projects/ljwx/repositories

# 查看镜像 tags
docker buildx imagetools inspect harbor.omniverseai.net/ljwx/[app]:latest

# 手动拉取镜像
docker pull harbor.omniverseai.net/ljwx/[app]:main-[sha]
```

### Git 操作

```bash
# 克隆 ljwx-deploy
git clone http://192.168.1.83:33000/gao/ljwx-deploy.git

# 查看最近提交
cd ljwx-deploy
git log --oneline -10

# 查看特定应用的变更历史
git log --oneline -- apps/ljwx-website/overlays/ljwx-website-dev/kustomization.yaml

# 回滚到上一个版本
git revert HEAD
git push origin main
# Argo CD 会自动回滚部署
```

---

## ⚡ 快速测试流程

### 测试完整 GitOps 流程

```bash
# 1. 修改代码
cd /path/to/project
echo "// Test CI/CD" >> src/App.tsx

# 2. 提交并推送
git add .
git commit -m "test: verify GitOps flow"
git push origin main

# 3. 观察 CI (约 3-5 分钟)
# http://192.168.1.83:33000/gao/[project]/actions
# ✅ Lint & Test → ✅ Build & Push → ✅ Update Deploy

# 4. 观察 CD (约 30 秒)
watch kubectl get pods -n [namespace] -l app=[app-name]
# 应看到旧 Pod Terminating，新 Pod Running

# 5. 验证镜像更新
kubectl describe pod -n [namespace] -l app=[app-name] | grep Image:
# 应显示新的 image tag: main-[new-sha]

# 6. 验证健康检查
kubectl exec -n [namespace] deployment/[app-name] -- \
  wget -q -O- http://localhost/health
# 应返回: healthy
```

---

## 🎯 Workflow 配置关键点

### Runner 选择

```yaml
# 轻量级任务 (lint, test)
runs-on: ubuntu-latest  # K8s runner

# Docker 构建任务
runs-on: docker-builder  # 宿主机 runner (macos 标签也可用)
```

### Multi-arch 构建

```yaml
# ✅ 正确: 使用 buildx + atomic push
- name: Set up Docker Buildx
  run: |
    docker buildx create --name ci-builder --use || docker buildx use ci-builder
    docker buildx inspect --bootstrap

- name: Build and push
  run: |
    docker buildx build \
      --platform linux/amd64,linux/arm64 \
      --push \
      .

# ❌ 错误: 分离的 build 和 push
docker build -t image .
docker push image  # 会导致竞态条件
```

### Kustomize 镜像更新

```yaml
# ✅ 正确: 使用 yq 更新 kustomization.yaml
cd apps/my-app/overlays/my-app-dev
yq eval ".images[0].newTag = \"${IMAGE_TAG}\"" -i kustomization.yaml

# ❌ 错误: 尝试更新 Helm values.yaml
yq eval ".image.tag = \"${IMAGE_TAG}\"" -i values.yaml  # 不存在
```

---

## 🔐 安全提示

### Secrets 安全使用

```yaml
# ✅ 安全的 Secrets 使用
- run: echo "${{ secrets.PASSWORD }}" | docker login ... --password-stdin

# ❌ 危险: 泄露 Secrets
- run: echo "Password is ${{ secrets.PASSWORD }}"  # 会在日志中显示
- run: docker login -p ${{ secrets.PASSWORD }} ...  # 会在进程列表中显示
```

### Token 权限最小化

```bash
# DEPLOY_REPO_TOKEN 需要的权限:
✅ repo                # 读取仓库
✅ write:repository   # 写入仓库

# 不需要的权限:
❌ admin:org          # 组织管理
❌ delete:packages    # 删除包
❌ admin:gpg_key      # GPG 密钥管理
```

---

## 📊 配置时间对比

### 使用本指南

```
Organization Secrets (一次性): 5 分钟
新项目 CI 配置: 2 分钟
新项目 CD 配置: 8 分钟
---------------------------------
总计 (首次): 15 分钟
总计 (后续每个项目): 10 分钟
```

### 传统方式

```
每个项目 Secrets 配置: 5 分钟
手动编写 Workflow: 30 分钟
手动创建 K8s 资源: 20 分钟
手动配置 Argo CD: 10 分钟
---------------------------------
总计 (每个项目): 65 分钟
```

**效率提升: 85%** 🚀

---

## 💡 故障排查速查表

| 问题 | 排查命令 | 常见原因 |
|------|----------|----------|
| CI 失败 | 查看 Gitea Actions 日志 | Runner 标签错误、Secrets 未配置 |
| Build 失败 | `docker buildx ls` | buildx 未初始化 |
| Push 失败 | `docker login harbor.omniverseai.net` | Harbor 凭据错误 |
| Update Deploy 未执行 | 检查 ljwx-deploy 最新 commit | Token 权限不足、路径错误 |
| Argo CD 未同步 | `kubectl get application -n argocd` | Application 文件名不匹配 pattern |
| Pod 启动失败 | `kubectl describe pod -n [ns]` | 资源不足、镜像拉取失败 |
| Health check 失败 | `kubectl logs -n [ns]` | /health 端点不存在 |

---

## 🎓 学习路径

### 阶段 1: 基础配置 (第 1 天)
1. 阅读 [GITEA-SECRETS-SETUP.md](GITEA-SECRETS-SETUP.md)
2. 配置 Organization Secrets
3. 测试现有项目 (ljwx-website)

### 阶段 2: 新项目实践 (第 2-3 天)
1. 阅读 [GITEA-CICD-SETUP-GUIDE.md](GITEA-CICD-SETUP-GUIDE.md)
2. 为一个新项目配置完整 CI/CD
3. 测试完整 GitOps 流程

### 阶段 3: 高级应用 (第 4-5 天)
1. 阅读 [ARGOCD-APP-MANAGEMENT.md](ARGOCD-APP-MANAGEMENT.md)
2. 理解 App of Apps 模式
3. 阅读 [NAMESPACE-STRATEGY.md](NAMESPACE-STRATEGY.md)
4. 规划多环境部署 (dev/staging/prod)

### 阶段 4: 运维优化 (持续)
1. 监控 CI/CD 性能
2. 优化 Docker 镜像大小
3. 调整资源配额
4. 实施安全最佳实践

---

**🎉 开始使用 Gitea GitOps，享受自动化部署的乐趣！**
