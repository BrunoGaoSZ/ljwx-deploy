# envs 目录说明（冻结）

截至 `2026-03-05`，`envs/` 仅作为历史快照/兼容参考，不再作为 GitOps 主发布入口。

当前主路径：

- 入列：`release/queue.yaml`
- 映射：`release/services*.yaml`
- 部署触发：`apps/*/overlays/*/kustomization.yaml` 由 promoter 更新
- 证据链：`evidence/records/*` + `evidence/index.json`

规则：

1. 常规发布流程不得依赖 `envs/` 内容变更。
2. 若必须修改 `envs/`（兼容或迁移任务），需走 `platform-admin` 特殊审批路径。
3. 新服务接入请使用 `factory/onboarding/services.catalog.yaml` 与 `scripts/factory/onboard_services.sh`。

