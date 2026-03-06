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

平台基线定义位于：

- `factory/onboarding/namespace-profiles.yaml`
- `factory/onboarding/capability-profiles.yaml`
- `factory/onboarding/service-templates.yaml`
- `factory/onboarding/ingress-profiles.yaml`

推荐优先使用模板化写法：

- 最少只填：`service`、`environment`、`template`
- 现有项目按需追加：`overlay_name`、`image_repo`、`smoke_host`、`smoke_path`、`smoke_port`
- 需要公网域名 + HTTPS 的服务，优先用 `public-service` 或 `public-web-service`；若沿用其他模板，则显式补 `ingress_profile`、`public_host`、`public_path`、`public_service_name`、`public_service_port`
- 一个 overlay 下如果有多个发布镜像/多个 smoke 服务，改用 `template: multi-image-service` + `components`
- 共享 namespace 或已有 cluster 历史清单的旧项目：单镜像优先用 `batch-legacy-service`，多镜像优先用 `batch-multi-image-service`
- 只有确实偏离标准命名时，才显式写 `deploy_namespace`、`argocd_app`、`argocd_app_file`

公网 HTTPS 平台基线由以下 GitOps Application 统一管理：

- `argocd-apps/03-cert-manager-dev.yaml`
- `argocd-apps/04-cert-manager-config-dev.yaml`

兼容旧清单的 `ClusterIssuer` 名称仍为 `dnspod-letsencrypt`，当前实现已经切到 cert-manager + Traefik HTTP01。

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
- `apps/<service>/overlays/<env>/ingress.yaml`（声明 `public_host` 时）
- `argocd-apps/<xx>-<service>-dev.yaml`
- `apps/<service>/overlays/<env>/runtime-contract/*`
- `cluster/namespace-<namespace>.yaml`
- `cluster/<service>-<env>-application.yaml`
- `cluster/kustomization.yaml` 资源引用

## Step B: 服务仓接入标准 workflow

在服务仓执行（来自 `ljwx-workflow-templates`）：

```bash
bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard.sh --repo "$PWD" --service <service-name>
```

如果服务需要公网域名 + HTTPS，新项目优先直接使用：

```bash
bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard.sh \
  --repo "$PWD" \
  --service <service-name> \
  --service-template public-service \
  --public-host <domain>
```

前端类服务优先改用 `--service-template public-web-service`。

生成：

- `.github/workflows/build-and-enqueue.yml`
- `.github/workflows/k3s-perf-observability.yml`
- `.gitops/onboarding.catalog.snippet.yaml`

并自动包含 PR Gate：

- 调用 `ljwx-workflow-templates/.github/workflows/gitops-onboarding-gate.yml`
- 未接入完成时阻断 PR 合并

## Step C: 验证

```bash
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml dry-run
python3 scripts/promoter/validate_queue.py --queue release/queue.yaml
bash scripts/verify.sh
```

如果该服务声明了 `public_host`，还要补一轮公网验收：

1. `argocd` 中对应 Application 为 `Synced` / `Healthy`
2. `kubectl get certificate -A` 中证书状态为 `Ready=True`
3. `curl -I https://<public-host>` 可成功握手，浏览器访问无证书告警

## 4. 老项目接入（仅补流程，不改业务代码）

1. 保留现有构建方式，先接入 `build-and-enqueue` workflow。
2. 在 deploy repo 建立 service map 与 overlay 映射。
3. 如果一个 overlay 下挂多个镜像或多个 service key，使用 `multi-image-service` + `components` 统一生成 release/smoke 映射。
4. 如果共享 namespace 或已有 cluster 历史文件，单镜像优先用 `batch-legacy-service`，多镜像优先用 `batch-multi-image-service`，不要硬迁 cluster baseline。
5. 补 smoke endpoint。
6. 通过一轮 queue->promoter->argocd->smoke->evidence 验证闭环。

说明：新的公网接入口径统一走 `Traefik + cert-manager + Let's Encrypt HTTP01`。现有手写 `nginx`/HTTP-only ingress 先视为历史兼容，后续再单独迁移。

## 5. 生产发布接入补充（必须）

1. `prod` Application 与 `deploy-promoter-prod` 只放在 `cluster-prod/`，不要放到本地 `cluster/`。
2. 生产集群使用 `argocd-apps/02-cluster-prod-bootstrap.yaml` 作为 bootstrap 入口。
3. 需要拉私有镜像的 prod namespace 必须带标签：`registry-sync.ljwx.io/enabled=true`，由 `registry-pull-secret-sync` 自动下发 `harbor-registry/ghcr-pull/regcred`。

## 6. 三个重点项目接入口径（当前）

1. `ljwx-website`：已在 `ljwx-deploy` 管理，需保持映射与健康状态一致。
2. `ljwx-dify`：使用 `multi-image-service` + `components` 统一管理 `ljwx-dify` / `ljwx-dify-web`，不再手工维护额外 release/smoke 条目。
3. `ljwx-chat`：新项目按“新项目快速接入”执行，优先 `dev`，再扩到 `prod`。

## 7. 必过门禁

1. 禁止手工改集群作为长期状态来源。
2. 禁止 `envs/` 作为主发布入口（仅历史兼容）。
3. 变更必须经 PR 审核。
4. Secret 禁止明文入库。
5. 禁止在本地 `cluster/` 里管理 prod Application（防止误部署到本机集群）。

## 8. 常见错误

1. 只改服务仓，不改 deploy repo 映射。
2. overlay 路径和 argocd app 名不一致。
3. smoke endpoint 未配置，导致证据链断裂。
4. 使用脚本直发覆盖了 GitOps 状态，造成漂移。
5. 在 `onboard_services.sh` 之外另写 cluster 清单，覆盖 namespace baseline 或 Argo Application，造成漂移。
6. prod namespace 没有 `registry-sync.ljwx.io/enabled=true`，导致 `ImagePullBackOff`。
