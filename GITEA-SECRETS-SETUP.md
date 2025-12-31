# Gitea Organization Secrets 配置指南

## 📋 目标

配置组织级别的 Secrets，实现一次配置、所有项目共享，无需在每个项目中重复配置。

## 🎯 方案选择

### 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Organization Secrets** | ✅ 一次配置<br>✅ 所有项目共享<br>✅ 集中管理 | ⚠️ 需要 Organization | ⭐⭐⭐⭐⭐ |
| **Repository Secrets** | ✅ 项目隔离 | ❌ 每个项目都要配置<br>❌ 维护成本高 | ⭐⭐ |
| **Global Runner Secrets** | ✅ 全局可用 | ❌ 不安全<br>❌ 难以管理 | ⭐ |

**推荐**: 使用 Organization Secrets

## 🚀 快速配置 (Organization Secrets)

### Step 1: 检查当前组织结构

```bash
# 检查你的 Gitea 项目所属组织
# 访问: http://192.168.1.83:33000/gao

# 确认所有项目都在 "gao" 组织/用户下:
# - ljwx-website
# - ljwx-deploy
# - backend
# - frontend
# - quality-dashboard
# - (其他项目)
```

### Step 2: 配置 Organization Secrets

#### 方式 1: Web UI 配置 (推荐)

1. **访问组织设置**
   ```
   http://192.168.1.83:33000/gao
   ```

2. **导航到 Secrets 页面**
   ```
   组织首页 → Settings → Secrets (或 Actions → Secrets)
   ```

3. **添加以下 Secrets**

   **Secret 1: HARBOR_USERNAME**
   ```
   Name: HARBOR_USERNAME
   Value: admin (或你的 Harbor 用户名)
   ```

   **Secret 2: HARBOR_PASSWORD**
   ```
   Name: HARBOR_PASSWORD
   Value: [你的 Harbor 密码]
   ```

   **Secret 3: DEPLOY_REPO_TOKEN**
   ```
   Name: DEPLOY_REPO_TOKEN
   Value: [你的 Gitea Personal Access Token]
   ```

4. **验证配置**
   - 点击 "Add Secret" 后应该看到 secret 列表
   - 确认所有 3 个 secrets 都已添加

#### 方式 2: Gitea API 配置 (批量)

```bash
# 设置变量
GITEA_URL="http://192.168.1.83:33000"
ORG_NAME="gao"
GITEA_TOKEN="your-admin-token"  # 需要 admin 或 owner 权限

# 添加 HARBOR_USERNAME
curl -X PUT "${GITEA_URL}/api/v1/orgs/${ORG_NAME}/actions/secrets/HARBOR_USERNAME" \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "data": "admin"
  }'

# 添加 HARBOR_PASSWORD
curl -X PUT "${GITEA_URL}/api/v1/orgs/${ORG_NAME}/actions/secrets/HARBOR_PASSWORD" \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "data": "your-harbor-password"
  }'

# 添加 DEPLOY_REPO_TOKEN
curl -X PUT "${GITEA_URL}/api/v1/orgs/${ORG_NAME}/actions/secrets/DEPLOY_REPO_TOKEN" \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "data": "your-deploy-token"
  }'
```

### Step 3: 生成 DEPLOY_REPO_TOKEN (如果还没有)

```bash
# 1. 访问个人设置
http://192.168.1.83:33000/user/settings/applications

# 2. 生成新的访问令牌
Name: gitea-actions-deploy
Scopes:
  - repo (必须)
  - write:repository (必须)

# 3. 复制生成的 token
# 示例: 7ea68abccfb9de287305ab23b82c8e9a66fb6814

# 4. 将 token 添加到 Organization Secrets (见 Step 2)
```

### Step 4: 更新项目 Workflow (移除项目级 Secrets)

现在项目的 `.gitea/workflows/ci.yaml` 可以直接使用 Organization Secrets，无需任何修改：

```yaml
# ✅ 直接使用，无需在项目中配置
- name: Log in to Harbor
  run: echo "${{ secrets.HARBOR_PASSWORD }}" | docker login ${{ env.REGISTRY }} -u "${{ secrets.HARBOR_USERNAME }}" --password-stdin

- name: Update deployment repository
  run: |
    git clone http://gao:${{ secrets.DEPLOY_REPO_TOKEN }}@192.168.1.83:33000/gao/ljwx-deploy.git /tmp/ljwx-deploy
```

**优先级规则**:
1. Repository Secrets (项目级) - 最高优先级
2. Organization Secrets (组织级) - 如果项目没有配置
3. Global Secrets (全局) - 最低优先级

### Step 5: 清理项目级 Secrets (可选)

如果之前在项目中配置了 Secrets，现在可以删除：

```bash
# 访问每个项目的 Settings → Secrets
http://192.168.1.83:33000/gao/ljwx-website/settings/secrets
http://192.168.1.83:33000/gao/backend/settings/secrets
http://192.168.1.83:33000/gao/frontend/settings/secrets

# 删除以下 Secrets (因为已经在 Organization 级别配置):
# - HARBOR_USERNAME
# - HARBOR_PASSWORD
# - DEPLOY_REPO_TOKEN
```

## ✅ 验证配置

### 测试 1: 检查 Organization Secrets

```bash
# 访问组织 Secrets 页面
http://192.168.1.83:33000/gao/settings/secrets

# 应该看到:
# - HARBOR_USERNAME
# - HARBOR_PASSWORD
# - DEPLOY_REPO_TOKEN
```

### 测试 2: 新项目自动可用

```bash
# 1. 创建新项目
http://192.168.1.83:33000/repo/create

# 2. 添加 workflow 文件 (使用 secrets)
mkdir -p .gitea/workflows
cat > .gitea/workflows/test.yaml <<'EOF'
name: Test Secrets
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Test Harbor login
        run: |
          echo "Testing Harbor credentials..."
          docker login harbor.omniverseai.net -u "${{ secrets.HARBOR_USERNAME }}" --password-stdin <<< "${{ secrets.HARBOR_PASSWORD }}"
          echo "✅ Login successful!"
EOF

# 3. 提交并推送
git add .gitea/workflows/test.yaml
git commit -m "test: verify organization secrets"
git push origin main

# 4. 查看 Actions 运行结果
# 应该显示 "✅ Login successful!"
```

### 测试 3: 现有项目验证

```bash
# 在 ljwx-website 项目中触发 CI
cd /path/to/ljwx-website
git commit --allow-empty -m "test: verify org secrets"
git push origin main

# 查看 Actions 日志
http://192.168.1.83:33000/gao/ljwx-website/actions

# 检查 Build & Push job:
# ✅ Harbor 登录成功
# ✅ 镜像推送成功
# ✅ ljwx-deploy 更新成功
```

## 🔐 Secrets 管理最佳实践

### 1. Secrets 命名规范

```yaml
# ✅ 推荐: 清晰的语义命名
HARBOR_USERNAME
HARBOR_PASSWORD
DEPLOY_REPO_TOKEN
DOCKER_REGISTRY_URL

# ❌ 避免: 模糊的命名
SECRET1
TOKEN
PASSWORD
```

### 2. Secrets 轮换策略

```bash
# 定期更新 Secrets (建议 90 天)

# 1. 生成新的 DEPLOY_REPO_TOKEN
http://192.168.1.83:33000/user/settings/applications

# 2. 更新 Organization Secret
http://192.168.1.83:33000/gao/settings/secrets
# 编辑 DEPLOY_REPO_TOKEN → 输入新 token

# 3. 撤销旧 token
http://192.168.1.83:33000/user/settings/applications
# 删除旧的 token

# 4. 验证所有项目仍正常工作
# 触发 CI 测试
```

### 3. Secrets 作用域控制

```yaml
# Organization Secrets 适用于:
✅ 共享的基础设施凭据 (Harbor, Gitea)
✅ 通用的 API tokens
✅ 部署凭据

# Repository Secrets 适用于:
✅ 项目特定的凭据
✅ 需要隔离的敏感信息
✅ 不同环境的配置 (dev/staging/prod)
```

### 4. 安全检查清单

```bash
# ✅ 定期检查
- [ ] Secrets 是否有过期时间
- [ ] Token 权限是否最小化
- [ ] 是否有未使用的 Secrets
- [ ] Workflow 日志是否泄露 Secrets
- [ ] 是否定期轮换凭据

# ❌ 避免
- [ ] 在 Workflow 中 echo Secrets
- [ ] 将 Secrets 写入文件
- [ ] 在 PR 中暴露 Secrets
- [ ] 使用过于宽泛的权限
```

## 📊 当前项目配置总结

### 组织级别 (gao)

配置以下 3 个 Organization Secrets，所有项目自动可用：

```yaml
HARBOR_USERNAME: admin
HARBOR_PASSWORD: [Harbor 管理员密码]
DEPLOY_REPO_TOKEN: [Gitea Personal Access Token with repo scope]
```

### 项目列表 (自动继承)

以下项目无需单独配置，自动使用 Organization Secrets：

```
✅ ljwx-website       - 已验证
✅ ljwx-deploy        - 仅被引用，不需要 CI
✅ backend            - 可配置 CI
✅ frontend           - 可配置 CI
✅ quality-dashboard  - 可配置 CI
✅ nginx              - 可配置 CI
✅ [未来新项目]       - 自动可用
```

### Workflow 模板 (通用)

```yaml
# 所有项目都使用相同的 secrets 引用
secrets.HARBOR_USERNAME
secrets.HARBOR_PASSWORD
secrets.DEPLOY_REPO_TOKEN

# 无需在每个项目中重复配置！
```

## 🎯 快速开始新项目

现在为新项目添加 CI/CD 只需 2 步：

```bash
# Step 1: 创建 workflow 文件
mkdir -p .gitea/workflows
cp /path/to/ljwx-website/.gitea/workflows/ci.yaml .gitea/workflows/

# Step 2: 修改项目名称
sed -i 's/ljwx\/ljwx-website/ljwx\/my-new-app/g' .gitea/workflows/ci.yaml

# ✅ 完成！Secrets 自动可用，无需配置
```

## 🔄 迁移现有项目

如果现有项目已经配置了 Repository Secrets：

```bash
# 1. 验证 Organization Secrets 已配置
curl -X GET "http://192.168.1.83:33000/api/v1/orgs/gao/actions/secrets" \
  -H "Authorization: token ${GITEA_TOKEN}"

# 2. 删除项目级 Secrets (可选)
# http://192.168.1.83:33000/gao/[project]/settings/secrets

# 3. 测试 workflow
git commit --allow-empty -m "test: verify org secrets"
git push origin main

# 4. 检查运行结果
# http://192.168.1.83:33000/gao/[project]/actions
```

## 📝 总结

### 配置前 (每个项目都要配置)

```
ljwx-website    → Settings → Secrets → HARBOR_USERNAME, HARBOR_PASSWORD, DEPLOY_REPO_TOKEN
backend         → Settings → Secrets → HARBOR_USERNAME, HARBOR_PASSWORD, DEPLOY_REPO_TOKEN
frontend        → Settings → Secrets → HARBOR_USERNAME, HARBOR_PASSWORD, DEPLOY_REPO_TOKEN
quality-dash... → Settings → Secrets → HARBOR_USERNAME, HARBOR_PASSWORD, DEPLOY_REPO_TOKEN
[每个新项目都要重复配置] ❌
```

### 配置后 (一次配置，全局共享)

```
gao (Organization) → Settings → Secrets → HARBOR_USERNAME, HARBOR_PASSWORD, DEPLOY_REPO_TOKEN
  ↓
  └─ 所有项目自动继承 ✅
     - ljwx-website
     - backend
     - frontend
     - quality-dashboard
     - [未来所有新项目]
```

**效果**:
- ✅ 配置时间: 15 分钟 → 2 分钟
- ✅ 维护成本: 降低 80%
- ✅ 新项目开箱即用
- ✅ 集中管理，安全性提升

🎉 **一次配置，永久受益！**
