# Onboarding Automation (Template-based)

目标：让新项目和历史项目都能快速接入同一套闭环：

`queue -> promoter -> deploy -> smoke -> evidence -> pages`

## 1. 填写 catalog

编辑：

- `factory/onboarding/services.catalog.yaml`

每个服务定义一项，包括：

- `service`, `environment`
- `overlay_path`
- `kustomize_image_name`, `harbor_image`
- `argocd_app`, `deploy_namespace`
- `smoke_endpoint`
- `profiles` (`local-k3s`, `orbstack-k3s-cn`)
- `scaffold_app`（是否生成应用骨架）
- `generate_argocd_app` + `argocd_app_file`

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

可选生成：

- `apps/<service>/base/*`
- `apps/<service>/overlays/<env>/kustomization.yaml`
- `argocd-apps/*.yaml`

## 4. 接入后验收

```bash
python3 scripts/promoter/validate_queue.py --queue release/queue.yaml
bash scripts/verify.sh
```

然后按标准路径验证：

- 入 queue
- promoter 推进
- Argo 同步
- smoke 写回
- nightly-evidence 发布 Pages
