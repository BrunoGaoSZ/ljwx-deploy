# START HERE: GitOps 接入指南（新 Codex 进程必读）

目标：让任何新启动的 Codex 进程在 10 分钟内理解并执行当前标准流程。

## 1. 先理解这条主链路

`service repo build -> enqueue release/queue.yaml -> promoter 更新 overlay -> ArgoCD 同步 -> smoke -> evidence/pages`

对应仓库职责：

- `ljwx-workflow-templates`：服务仓可复用 workflow 模板
- `ljwx-deploy`：唯一部署真相源（queue、service map、argocd apps、overlays、evidence）

## 2. 新进程第一次进入时必须先读

1. `README.md`
2. `release/README.md`
3. `docs/onboarding-automation.md`
4. `docs/service-repo-workflow-snippet.md`
5. `docs/argocd-dev-autosync.md`

并先执行自动扫描：

```bash
bash scripts/ops/scan-gitops-context.sh --repo "$PWD"
```

## 3. 新项目快速接入（推荐）

## Step A: 在 deploy repo 注册服务映射

编辑 `factory/onboarding/services.catalog.yaml`，新增服务项。

然后执行：

```bash
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml dry-run
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml apply
```

自动更新：

- `release/services.yaml`
- `release/services.local-k3s.yaml`
- `release/services.orbstack-k3s-cn.yaml`
- `scripts/smoke/targets.local-k3s.json`
- `scripts/smoke/targets.orbstack-k3s-cn.json`

按需生成：

- `apps/<service>/base/*`
- `apps/<service>/overlays/<env>/kustomization.yaml`
- `argocd-apps/<xx>-<service>-dev.yaml`

## Step B: 服务仓接入标准 workflow

在服务仓执行（来自 `ljwx-workflow-templates`）：

```bash
bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard.sh --repo "$PWD" --service <service-name>
```

生成：

- `.github/workflows/build-and-enqueue.yml`
- `.github/workflows/k3s-perf-observability.yml`
- `.gitops/onboarding.catalog.snippet.yaml`

并自动包含 PR Gate：

- 调用 `ljwx-workflow-templates/.github/workflows/gitops-onboarding-gate.yml`
- 未接入完成时阻断 PR 合并

## Step C: 验证

```bash
python3 scripts/promoter/validate_queue.py --queue release/queue.yaml
bash scripts/verify.sh
```

## 4. 老项目接入（仅补流程，不改业务代码）

1. 保留现有构建方式，先接入 `build-and-enqueue` workflow。
2. 在 deploy repo 建立 service map 与 overlay 映射。
3. 补 smoke endpoint。
4. 通过一轮 queue->promoter->argocd->smoke->evidence 验证闭环。

## 5. 三个重点项目接入口径（当前）

1. `ljwx-website`：已在 `ljwx-deploy` 管理，需保持映射与健康状态一致。
2. `ljwx-dify`：必须纳入同一 GitOps 主链路，不再采用独立脚本直发。
3. `ljwx-chat`：新项目按“新项目快速接入”执行，优先 `dev`，再扩到 `prod`。

## 6. 必过门禁

1. 禁止手工改集群作为长期状态来源。
2. 禁止 `envs/` 作为主发布入口（仅历史兼容）。
3. 变更必须经 PR 审核。
4. Secret 禁止明文入库。

## 7. 常见错误

1. 只改服务仓，不改 deploy repo 映射。
2. overlay 路径和 argocd app 名不一致。
3. smoke endpoint 未配置，导致证据链断裂。
4. 使用脚本直发覆盖了 GitOps 状态，造成漂移。
