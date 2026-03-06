# Onboarding Automation (Template-based)

目标：让新项目和历史项目都能快速接入同一套闭环：

`queue -> promoter -> deploy -> smoke -> evidence -> pages`

## 1. 填写 catalog

编辑：

- `factory/onboarding/services.catalog.yaml`

每个服务定义一项，包括：

- `service`, `environment`
- `template`（推荐，来自 `factory/onboarding/service-templates.yaml`）
- `components`（可选；用于一个 overlay/Argo app 下挂多个 release/smoke service key 的旧项目）
- `overlay_name`, `image_repo`, `smoke_host`, `smoke_path`, `smoke_port`（按需 override）
- `overlay_path`
- `kustomize_image_name`, `harbor_image`
- `argocd_app`, `deploy_namespace`
- `smoke_endpoint`
- `profiles` (`local-k3s`, `orbstack-k3s-cn`)
- `namespace_profile`
- `registry_profile`
- `runtime_secret_profile`
- `capabilities`
- `ingress_profile`
- `public_host`, `public_path`
- `public_service_name`, `public_service_port`
- `ingress_class_name`, `cluster_issuer`, `tls_secret_name`
- `cluster_bootstrap`（可选；关闭后不生成 `cluster/namespace-*` 和 `cluster/*-application.yaml`）
- `scaffold_app`（是否生成应用骨架）
- `generate_argocd_app` + `argocd_app_file`

平台 profile 来源：

- `factory/onboarding/namespace-profiles.yaml`
- `factory/onboarding/capability-profiles.yaml`
- `factory/onboarding/service-templates.yaml`
- `factory/onboarding/ingress-profiles.yaml`

推荐优先使用模板化 catalog。新项目通常只需要：

```yaml
- service: demo-api
  environment: dev
  template: service-default
```

老项目可在模板上追加少量 override：

```yaml
- service: legacy-web
  environment: dev
  template: legacy-service
  overlay_name: legacy-web-dev
  smoke_path: /
```

需要公网域名 + HTTPS 的服务，优先使用 `public-service` 或 `public-web-service`：

```yaml
- service: demo-web
  environment: dev
  template: public-web-service
  public_host: demo.lingjingwanxiang.cn
```

当前标准公网 profile 为 `traefik-letsencrypt-public`：

- 统一生成 overlay `ingress.yaml`
- 默认 `ingressClassName: traefik`
- 默认启用 TLS 和 `cert-manager.io/cluster-issuer: dnspod-letsencrypt`
- 默认路径 `/`
- 默认后端端口 `80`

兼容旧清单的 issuer 名仍叫 `dnspod-letsencrypt`，但实现已经切到 cert-manager + Traefik HTTP01。

多镜像旧项目推荐使用 `multi-image-service` + `components`：

```yaml
- service: ljwx-dify
  environment: dev
  template: multi-image-service
  overlay_name: ljwx-dify-dev
  components:
    - service: ljwx-dify
      image_repo: ljwx-dify-api
      smoke_host: api
      smoke_port: "5001"
      smoke_path: /health
    - service: ljwx-dify-web
      image_repo: ljwx-dify-web
      smoke_host: web
      smoke_port: "3000"
      smoke_path: /
```

约束：

- 多组件模式要求复用已有 overlay，因此应保持 `scaffold_app: false`
- `components[*].service` 必须唯一
- smoke 目标按 `components[*]` 生成；未声明 smoke 的 component 不会写入 smoke target

共享 namespace 或已有历史 cluster 清单的旧项目，可继续由 catalog 管理 release/argocd，但关闭 cluster bootstrap。单镜像优先用 `batch-legacy-service`：

```yaml
- service: ljwx-stock-agent
  environment: dev
  template: batch-legacy-service
  overlay_path: apps/stock-agent/overlays/ljwx-stock/kustomization.yaml
  deploy_namespace: ljwx-stock
  argocd_app: stock-agent-dev
  argocd_app_file: argocd-apps/81-stock-agent-dev.yaml
  ghcr_org: brunogao/ljwx-stock
  image_repo: ljwx-stock-agent
  smoke_host: stock-agent
  smoke_path: /v1/health
```

多镜像 batch 旧项目继续用 `batch-multi-image-service`：

```yaml
- service: ljwx-stock-qlib-predict
  environment: dev
  template: batch-multi-image-service
  overlay_path: apps/stock-etl/overlays/ljwx-stock/kustomization.yaml
  deploy_namespace: ljwx-stock
  argocd_app: stock-etl-qlib-predict-dev
  argocd_app_file: argocd-apps/80-stock-etl-qlib-predict-dev.yaml
  cluster_bootstrap: false
  components:
    - service: ljwx-stock-qlib-predict
      kustomize_image_name: ghcr.io/brunogao/ljwx-stock/ljwx-stock-qlib-predict
      harbor_image: harbor.eu.lingjingwanxiang.cn/ljwx/ljwx-stock-qlib-predict
    - service: ljwx-stock-kline-etl
      kustomize_image_name: ghcr.io/brunogao/ljwx-stock/ljwx-stock-kline-etl
      harbor_image: harbor.eu.lingjingwanxiang.cn/ljwx/ljwx-stock-kline-etl
```

旧的“全部显式字段”写法仍然兼容，但不再推荐作为默认接入方式。

## 2. dry-run 预览

```bash
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml dry-run
```

## 3. 执行接入

```bash
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml apply
```

脚本会自动更新：

- `release/services.yaml`
- `release/services.local-k3s.yaml`
- `release/services.orbstack-k3s-cn.yaml`
- `scripts/smoke/targets.local-k3s.json`
- `scripts/smoke/targets.orbstack-k3s-cn.json`

默认生成：

- `apps/<service>/base/*`
- `apps/<service>/overlays/<env>/kustomization.yaml`
- `apps/<service>/overlays/<env>/ingress.yaml`（声明 `public_host` 时）
- `argocd-apps/*.yaml`
- `apps/<service>/overlays/<env>/runtime-contract/contract.yaml`
- `apps/<service>/overlays/<env>/runtime-contract/*.secret.example.yaml`
- `apps/<service>/overlays/<env>/runtime-contract/README.md`
- `cluster/namespace-<namespace>.yaml`
- `cluster/<service>-<env>-application.yaml`
- `cluster/kustomization.yaml` 中的资源引用

如需仅处理 deploy 映射而不生成 cluster baseline，可设置：

```bash
ONBOARD_CLUSTER_BOOTSTRAP=false \
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml apply
```

## 4. 接入后验收

```bash
bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml dry-run
python3 scripts/promoter/validate_queue.py --queue release/queue.yaml
bash scripts/verify.sh
```

然后按标准路径验证：

- 入 queue
- promoter 推进
- Argo 同步
- smoke 写回
- nightly-evidence 发布 Pages

如果该服务对外暴露域名，还要额外确认：

- `argocd-apps/03-cert-manager-dev.yaml` 与 `argocd-apps/04-cert-manager-config-dev.yaml` 已同步
- `kubectl get certificate -A` 中对应域名证书为 `Ready=True`
- `curl -I https://<public-host>` 返回正常，浏览器访问无证书告警

说明：当前标准只覆盖 `Traefik + cert-manager` 的 k3s 公网接入口径。历史 `nginx`/HTTP-only ingress 暂未自动迁移。
