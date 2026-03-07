# Rollback Drill (Monthly)

目标：将“回滚能力”作为固定演练项，而不是仅在事故时临时验证。

## 范围

当前演练覆盖三类可回撤对象：

1. 路由配置回滚
2. 知识撤回与重新 publish
3. capability gateway profile 回滚

## 本地执行

```bash
bash scripts/ops/run_rollback_drill.sh
```

脚本行为：

1. 复制 `ljwx-deploy`、`ljwx-knowledge`、`ljwx-core-api` 到临时目录。
2. 对 `platform/routing/routes.dev.yaml` 打一次临时变更并恢复原文，再跑路由 contract 校验。
3. 对知识文档执行一次 `invalidate`，确认 dataset 移除后再 `publish` 恢复。
4. 对 `ljwx-core-api/config/tool_profiles.yaml` 打一次白名单变更并恢复，再跑 gateway tests。
5. 删除临时目录，不保留任何提交。

说明：

- 该演练不直接改 live cluster。
- 重点是证明 Git 配置、知识数据集、gateway profile 都存在清晰回滚点。

## CI 定时

工作流：`.github/workflows/monthly-rollback-drill.yml`

- 定时：每月一次
- 模式：临时副本内演练
- 目的：持续验证“可回滚”而非仅验证“可发布”
