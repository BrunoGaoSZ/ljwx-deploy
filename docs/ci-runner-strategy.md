# CI/Runner 策略说明

## 📋 概述

本文档说明 GitHub Actions Runner 的选择策略，帮助团队在 **GitHub-hosted runner** 和 **Self-hosted runner (ARC)** 之间做出正确决策。

**核心策略：**
- ✅ **默认使用 GitHub-hosted runner**（免费额度 + 零维护）
- ✅ **按需启用 ARC**（特殊场景：内网访问、大量构建、特殊硬件）
- ✅ **避免过早优化**（不要一开始就自建 runner）

---

## 🎯 快速决策树

```
你的项目需要 CI/CD 吗？
  ↓
是
  ↓
是否需要访问内网资源？
  ├─ 是 → 使用 ARC (Self-hosted)
  │         (例如：内网数据库、私有 API)
  │
  └─ 否 → 构建时间是否 > 10 分钟？
          ├─ 否 → 使用 GitHub-hosted runner ✅
          │         (大多数项目)
          │
          └─ 是 → 月构建次数是否 > 500 次？
                  ├─ 否 → 使用 GitHub-hosted runner ✅
                  │         (成本仍可接受)
                  │
                  └─ 是 → 考虑启用 ARC
                           (评估成本 vs 维护成本)
```

---

## 🔄 GitHub-hosted vs Self-hosted (ARC)

### 对比表

| 维度 | GitHub-hosted Runner | Self-hosted Runner (ARC) |
|------|---------------------|-------------------------|
| **成本** | 免费额度：2000 分钟/月<br>超出：$0.008/分钟 | K8s 节点成本：$50-200/月<br>维护成本：人力 |
| **维护** | ✅ 零维护（GitHub 管理） | ❌ 需要维护（更新、监控、扩缩容） |
| **安全性** | ✅ 每次构建全新环境<br>✅ 自动清理 | ⚠️ 需要配置安全策略<br>⚠️ 需要定期更新镜像 |
| **性能** | 标准：2 核 7GB<br>Large：4 核 16GB | 可自定义（2-16 核） |
| **启动速度** | 🟡 中等（10-30 秒） | 🟢 快速（2-10 秒） |
| **网络访问** | ✅ 公网<br>❌ 无法访问内网 | ✅ 公网 + 内网（K8s 集群内） |
| **并发构建** | ✅ 无限（GitHub 管理） | ⚠️ 受限于 K8s 节点资源 |
| **缓存** | ✅ 支持 actions/cache | ✅ 支持 + 可自建缓存层 |
| **特殊硬件** | ❌ 无 GPU/特殊设备 | ✅ 可配置 GPU/特殊设备 |
| **适用场景** | 🎯 大多数项目 | 🎯 内网访问、大量构建、特殊硬件 |

---

## ✅ 默认策略：使用 GitHub-hosted Runner

### 为什么默认选择 GitHub-hosted？

#### 1. **免费额度充足**

GitHub 提供慷慨的免费额度：

- **公共仓库：** 无限免费分钟
- **私有仓库（个人账户）：** 2000 分钟/月
- **私有仓库（团队账户）：** 3000 分钟/月
- **私有仓库（企业账户）：** 50000 分钟/月

**实际案例：**
```
项目：youngth-guard-backend
构建时间：5 分钟/次
每日提交：10 次
月构建次数：300 次
月消耗分钟：1500 分钟

结论：免费额度完全够用 ✅
```

#### 2. **零维护成本**

GitHub-hosted runner 完全由 GitHub 管理：

- ✅ 自动更新操作系统和工具链
- ✅ 自动扩缩容（并发构建）
- ✅ 自动清理（每次构建全新环境）
- ✅ 无需监控和告警
- ✅ 无需担心资源不足

**对比 Self-hosted：**
- ❌ 需要维护 ARC 控制器
- ❌ 需要维护 runner 镜像
- ❌ 需要配置扩缩容策略
- ❌ 需要监控资源使用
- ❌ 需要定期更新依赖

#### 3. **安全性最佳**

每次构建都是全新的虚拟机：

- ✅ 完全隔离（无交叉污染）
- ✅ 无状态（自动清理密钥/缓存）
- ✅ 防止密钥泄露（构建结束即销毁）

#### 4. **快速上手**

无需配置，开箱即用：

```yaml
# .github/workflows/build.yml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest  # 就这么简单！

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t myapp .

      - name: Push to GHCR
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          docker push ghcr.io/${{ github.repository }}:${{ github.sha }}
```

---

## 🚀 何时启用 ARC (Self-hosted Runner)

### 场景 1：需要访问内网资源 ✅ 推荐

**问题：** GitHub-hosted runner 运行在公网，无法访问内网数据库/API。

**示例：**
- 需要连接内网 Postgres 数据库进行集成测试
- 需要调用内网 API 进行验证
- 需要访问内网 NFS/S3 存储

**解决方案：** 使用 ARC，runner 运行在 K8s 集群内，可访问内网服务。

```yaml
# .github/workflows/integration-test.yml
jobs:
  test:
    runs-on: self-hosted  # 使用 ARC

    steps:
      - name: Run integration tests
        run: |
          # 可以直接访问内网数据库
          export DB_HOST=postgres-lb.infra.svc.cluster.local
          pytest tests/integration/
```

### 场景 2：大量构建，成本优化 ⚠️ 需评估

**问题：** 超出免费额度，GitHub-hosted runner 费用高。

**成本对比：**

| 方案 | 月构建次数 | 月构建时间 | 月成本 |
|------|----------|----------|--------|
| GitHub-hosted | 1000 次 | 5000 分钟 | $24 (超出 3000 分钟) |
| GitHub-hosted | 5000 次 | 25000 分钟 | $176 |
| ARC (1 节点) | 无限 | 无限 | $50-100 (K8s 节点) + 维护 |

**决策：**
- 月构建 < 5000 分钟 → GitHub-hosted 更划算 ✅
- 月构建 > 10000 分钟 → 考虑 ARC
- 月构建 > 50000 分钟 → 强烈推荐 ARC

### 场景 3：特殊硬件需求 ✅ 推荐

**问题：** 需要 GPU、特殊 CPU 架构（ARM）、大内存。

**示例：**
- 机器学习模型训练（需要 GPU）
- 构建 ARM 架构镜像（Apple Silicon / Raspberry Pi）
- 大型 monorepo 构建（需要 32GB+ 内存）

**解决方案：** 使用 ARC，配置专用节点池。

```yaml
# ARC 配置：GPU 节点池
apiVersion: actions.summerwind.dev/v1alpha1
kind: RunnerDeployment
metadata:
  name: gpu-runner
spec:
  replicas: 1
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-accelerator: nvidia-tesla-t4
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
      containers:
        - name: runner
          resources:
            limits:
              nvidia.com/gpu: 1
```

### 场景 4：构建速度优化 🟡 可选

**问题：** GitHub-hosted runner 启动慢（10-30 秒）。

**对比：**
- GitHub-hosted：10-30 秒启动
- ARC (预热)：2-10 秒启动

**决策：**
- 构建频率低（< 50 次/天）→ 启动时间不重要 ✅
- 构建频率高（> 200 次/天）→ 考虑 ARC
- 需要快速反馈（如 PR 验证）→ 考虑 ARC

### 场景 5：合规性要求 ✅ 推荐

**问题：** 企业安全政策禁止使用公网 runner。

**示例：**
- 金融行业（需要数据本地化）
- 政府项目（需要在指定区域运行）
- 内部工具（禁止代码离开内网）

**解决方案：** 使用 ARC，确保所有构建在内网完成。

---

## 📊 成本分析

### GitHub-hosted Runner 成本

**定价（2025 年）：**
- Linux：$0.008/分钟
- Windows：$0.016/分钟
- macOS：$0.08/分钟

**实际案例：**

| 项目 | 构建时间 | 月构建次数 | 月消耗分钟 | 免费额度 | 超出分钟 | 月成本 |
|------|---------|----------|----------|---------|---------|--------|
| 小型项目 | 3 分钟 | 200 次 | 600 分钟 | 3000 | 0 | **$0** |
| 中型项目 | 8 分钟 | 500 次 | 4000 分钟 | 3000 | 1000 | **$8** |
| 大型项目 | 15 分钟 | 1000 次 | 15000 分钟 | 3000 | 12000 | **$96** |

### ARC (Self-hosted) 成本

**基础成本：**
- K8s 节点：$50-200/月（取决于云厂商和规格）
- 存储（缓存）：$10-20/月
- 网络流量：$5-15/月

**维护成本：**
- 初始搭建：4-8 小时
- 月度维护：2-4 小时/月
- 按工程师时薪 $50 计算：$100-200/月

**总成本：** $165-435/月

**适用场景：**
- 月构建分钟 > 20000 → ARC 成本更低
- 需要内网访问 → ARC 是唯一选择
- 团队规模 > 10 人 → 维护成本分摊

---

## 🔧 ARC 配置示例

### 前提条件

当前 `ljwx-deploy` 仓库已经配置了 ARC：

- ✅ ARC 控制器已部署（`infra/arc/`）
- ✅ RunnerDeployment 已配置（弹性伸缩）
- ✅ GHCR 认证已配置（imagePullSecrets）

### 查看当前 ARC 状态

```bash
# 查看 ARC 控制器
kubectl -n arc-systems get pods

# 查看 Runner 状态
kubectl -n arc-runners get runners

# 查看 RunnerDeployment
kubectl -n arc-runners get runnerdeployments
```

### 使用 ARC Runner

在 GitHub Actions workflow 中指定：

```yaml
# .github/workflows/build-with-arc.yml
name: Build with ARC

on:
  push:
    branches: [main]

jobs:
  build:
    # 使用 self-hosted runner
    runs-on: self-hosted

    steps:
      - uses: actions/checkout@v4

      - name: Build in Kubernetes
        run: |
          echo "Running in K8s cluster"
          echo "Can access internal services:"
          curl postgres-lb.infra.svc.cluster.local:5432

      - name: Build Docker image
        run: |
          docker build -t myapp .
          docker push ghcr.io/myorg/myapp:${{ github.sha }}
```

### 配置多个 Runner 类型

```yaml
# infra/arc/runner-deployment-standard.yaml
apiVersion: actions.summerwind.dev/v1alpha1
kind: RunnerDeployment
metadata:
  name: arc-runner-standard
  namespace: arc-runners
spec:
  replicas: 2
  template:
    spec:
      labels:
        - self-hosted
        - linux
        - x64
        - standard  # 自定义标签
      resources:
        requests:
          memory: "2Gi"
          cpu: "1000m"
        limits:
          memory: "4Gi"
          cpu: "2000m"
---
# infra/arc/runner-deployment-large.yaml
apiVersion: actions.summerwind.dev/v1alpha1
kind: RunnerDeployment
metadata:
  name: arc-runner-large
  namespace: arc-runners
spec:
  replicas: 1
  template:
    spec:
      labels:
        - self-hosted
        - linux
        - x64
        - large  # 自定义标签
      resources:
        requests:
          memory: "8Gi"
          cpu: "4000m"
        limits:
          memory: "16Gi"
          cpu: "8000m"
```

在 workflow 中使用：

```yaml
jobs:
  small-build:
    runs-on: [self-hosted, standard]  # 使用标准 runner
    steps:
      - run: npm run build

  large-build:
    runs-on: [self-hosted, large]  # 使用大内存 runner
    steps:
      - run: mvn clean install
```

---

## 📋 决策 Checklist

### 选择 GitHub-hosted Runner（推荐 ✅）

满足以下**所有**条件时，使用 GitHub-hosted：

- [ ] 无需访问内网资源
- [ ] 月构建分钟 < 10000（企业账户 < 50000）
- [ ] 无特殊硬件需求（GPU/大内存）
- [ ] 无合规性要求（数据可离开内网）
- [ ] 构建时间 < 30 分钟/次
- [ ] 团队规模较小（< 5 人）

**优势：**
- ✅ 零成本（免费额度内）
- ✅ 零维护
- ✅ 最高安全性
- ✅ 无限并发

### 选择 ARC (Self-hosted Runner)

满足以下**任一**条件时，考虑 ARC：

- [ ] 需要访问内网服务（数据库、API、存储）
- [ ] 月构建分钟 > 20000
- [ ] 需要 GPU 或特殊硬件
- [ ] 需要大内存（> 16GB）
- [ ] 合规性要求（数据不能离开内网）
- [ ] 需要自定义 runner 环境（特殊依赖）
- [ ] 团队规模较大（> 10 人，维护成本分摊）

**权衡：**
- ✅ 可访问内网
- ✅ 成本可控（大量构建时）
- ✅ 性能可定制
- ❌ 需要维护
- ❌ 初始搭建成本
- ❌ 需要安全加固

---

## 🚦 推荐配置策略

### 阶段 1：项目启动（0-3 个月）

**策略：100% GitHub-hosted**

```yaml
# .github/workflows/build.yml
jobs:
  build:
    runs-on: ubuntu-latest  # 默认
```

**原因：**
- 快速验证 CI/CD 流程
- 无需维护基础设施
- 免费额度足够

### 阶段 2：快速迭代（3-6 个月）

**策略：GitHub-hosted 为主，ARC 为辅**

```yaml
# .github/workflows/build.yml
jobs:
  # 普通构建：GitHub-hosted
  build:
    runs-on: ubuntu-latest

  # 集成测试（需要内网）：ARC
  integration-test:
    runs-on: self-hosted
    steps:
      - name: Test with internal DB
        run: pytest tests/integration/
```

**原因：**
- 大部分构建仍使用 GitHub-hosted
- 仅特殊场景使用 ARC
- 逐步积累 ARC 运维经验

### 阶段 3：规模化（6 个月+）

**策略：按需选择，精细化管理**

```yaml
# .github/workflows/matrix-build.yml
jobs:
  # 轻量级任务：GitHub-hosted
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: npm run lint

  # 标准构建：ARC (成本优化)
  build:
    runs-on: [self-hosted, standard]
    steps:
      - run: docker build .

  # 大型构建：ARC large
  build-monorepo:
    runs-on: [self-hosted, large]
    steps:
      - run: nx run-many --target=build --all

  # macOS 构建：GitHub-hosted (无 ARC macOS)
  build-ios:
    runs-on: macos-latest
    steps:
      - run: xcodebuild
```

**原因：**
- 成本最优
- 性能最优
- 维护成本可控

---

## 🔍 监控和优化

### GitHub-hosted Runner 监控

查看使用量：

1. GitHub 仓库 → Settings → Billing → Usage this month
2. 查看每个 workflow 的耗时：Actions → Workflow → Timing

**优化建议：**
- 使用 actions/cache 缓存依赖
- 并行执行独立 jobs
- 避免不必要的构建（配置 paths filter）

```yaml
# 优化示例：仅在代码变更时构建
on:
  push:
    paths:
      - 'src/**'
      - 'Dockerfile'
      - '.github/workflows/build.yml'
```

### ARC Runner 监控

```bash
# 查看 runner 资源使用
kubectl -n arc-runners top pods

# 查看 runner 日志
kubectl -n arc-runners logs -l app=runner

# 查看 HPA 状态（如果配置了自动扩缩容）
kubectl -n arc-runners get hpa
```

**优化建议：**
- 配置 HPA 根据队列长度扩缩容
- 使用 PVC 缓存 Docker 层
- 定期清理旧镜像

---

## 📖 相关文档

- `infra/arc/README.md` - ARC 部署和配置详解
- `docs/architecture-overview.md` - 平台架构说明
- `.github/workflows/` - 现有 workflow 示例
- GitHub Actions 官方文档：https://docs.github.com/en/actions
- ARC 项目：https://github.com/actions/actions-runner-controller

---

## 🎯 总结

**默认策略：** 使用 GitHub-hosted runner ✅

**例外场景：**
1. 需要访问内网 → ARC ✅
2. 月构建 > 20000 分钟 → 评估 ARC
3. 需要 GPU/特殊硬件 → ARC ✅
4. 合规性要求 → ARC ✅

**避免：**
- ❌ 过早优化（项目初期就自建 runner）
- ❌ 盲目跟风（看到别人用 ARC 就用）
- ❌ 忽视维护成本（只看节点成本，忽略人力）

**记住：**
> 最好的 runner 策略是**不需要维护的 runner**。
>
> 优先使用 GitHub-hosted，仅在必要时启用 ARC。
