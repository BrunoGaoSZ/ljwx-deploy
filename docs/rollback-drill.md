# Rollback Drill (Monthly)

目标：将“回滚能力”作为固定演练项，而不是仅在事故时临时验证。

## 范围

演练走标准链路，但只做 dry-run，不写入生产分支：

`latest promoted -> synthetic pending rollback entry -> promoter dry-run`

## 本地执行

```bash
bash scripts/ops/run_rollback_drill.sh
```

脚本行为：

1. 复制当前仓库到临时目录。
2. 读取 `release/queue.yaml`，取最近一条 `promoted` 记录。
3. 生成一条同镜像 digest 的 `pending` 回滚演练记录。
4. 校验队列结构并执行 promoter dry-run。
5. 删除临时目录，不保留任何提交。

## CI 定时

工作流：`.github/workflows/monthly-rollback-drill.yml`

- 定时：每月一次
- 模式：dry-run only
- 目的：持续验证“可回滚”而非仅验证“可发布”

