# 企业级智能客服系统实施清单（按 Sprint 执行，修订版）

更新时间：2026-03-05
适用环境：`ljwx-website`、`ljwx-chat`、`ljwx-dify`、`n8n`、`openclaw`、`k3s`（GitOps）

## 1. 角色与责任（必须绑定到具体人/组）

| 角色 | 建议负责人（示例） | 主要责任 | 必交付 |
|---|---|---|---|
| Platform Owner | `@team-platform` | GitOps、ArgoCD、集群与发布规范 | 发布门禁与回滚演练记录 |
| AI Owner | `@team-ai` | Dify Agent、RAG、模型路由、质量优化 | 模型路由策略与评测报告 |
| Workflow Owner | `@team-workflow` | n8n 工作流实现与运维 | 业务工作流与故障处理 Runbook |
| Data Owner | `@team-data` | 指标口径、报表、数据保留策略 | KPI 字段契约与口径文档 |
| Business Owner | `@team-product` | FAQ、业务规则、转人工策略 | 规则变更评审记录 |
| QA Owner | `@team-qa` | E2E、压测、安全测试、回归准入 | 测试报告与上线准入结论 |

说明：`@team-*` 需在启动 Sprint 前替换为真实 GitHub Team 或责任人。

## 2. Sprint 计划（可直接执行）

| Sprint | 周期 | Owner | 目标 | 关键任务 | 验收标准（DoD） |
|---|---|---|---|---|---|
| S1 基础就绪 | Week 1 | Platform Owner | 环境和发布链路稳定 | 1) 三个业务应用全部接入 GitOps 2) `infra-data`、`cluster-bootstrap` 健康 3) 镜像策略统一（GHCR→Harbor） | 1) Argo 应用全 `Synced/Healthy` 2) 四个入口按“第 5 节”定义全部可用 3) PR Gate 生效 |
| S2 数据链路最小闭环 | Week 2 | AI Owner + Workflow Owner | 跑通“知识库→对话→业务→观测”最小链路 | 1) 建立 5 类数据字段契约 2) 打通 Dify↔n8n 双向调用 3) Langfuse 可追踪全链路 | 1) 10 条样例问题可回放 trace 2) 业务透传成功率（`KPI-03`）≥ 99% 3) 无手工改集群 |
| S3 知识库与官网内容 | Week 3-4 | AI Owner + Business Owner | 建立内容生产与审批闭环 | 1) 知识库同步自动化（FAQ/文档/Notion） 2) 官网内容 PR 审批流 3) 未命中问题回流机制 | 1) 知识库命中率（`KPI-04`）≥ 85% 2) 官网内容变更必须经 PR 3) 回滚演练通过 |
| S4 业务透传与安全 | Week 5 | Workflow Owner + QA Owner | 业务工作流生产可用 | 1) 订单查询/工单创建/人工转接标准化 2) 鉴权与归属校验 3) 限流与错误分级 | 1) 越权访问拦截率（`KPI-06`）= 100% 2) P95 业务响应（`KPI-02`）< 3s 3) 失败有可追踪审计 |
| S5 运营与成本治理 | Week 6-8 | Data Owner + AI Owner | 指标、成本、质量可持续优化 | 1) KPI 口径固化 2) 每日/每周报自动推送 3) 模型分层路由与成本告警 | 1) 成本日报连续 14 天稳定 2) KPI 面板可用 3) 模型路由降本目标达成 |
| S6 上线与运维固化 | Week 9-12 | Platform Owner + QA Owner | 灰度、全量、运维标准化 | 1) 灰度发布策略 2) 应急回滚与故障演练 3) 运维 Runbook 与值班流程 | 1) 可用性（`KPI-01`）≥ 99.5% 2) 回滚演练 RTO（`KPI-07`）< 15 分钟 3) 线上变更全部可审计 |

## 3. KPI 口径契约（评审和验收统一口径）

| KPI ID | 指标 | 目标值 | 计算公式 | 统计窗口 | 数据源 | Owner |
|---|---|---|---|---|---|---|
| KPI-01 | 系统可用性 | `>= 99.5%` | `(总时间 - 不可用时间) / 总时间` | 日/周 | Prometheus + Argo | Platform Owner |
| KPI-02 | 首次响应时间（P95） | `< 3s` | `P95(first_reply_latency_ms) / 1000` | 日 | Langfuse Trace | AI Owner |
| KPI-03 | 业务透传成功率 | `>= 99%` | `成功调用数 / 总调用数` | 日 | n8n execution logs | Workflow Owner |
| KPI-04 | 知识库命中率 | `>= 85%` | `命中检索会话数 / 检索总会话数` | 日/周 | Dify + Langfuse | AI Owner |
| KPI-05 | AI 自主解决率 | `>= 70%` | `(总会话 - 转人工会话) / 总会话` | 日/周 | Dify + n8n analytics | Data Owner |
| KPI-06 | 越权拦截率 | `= 100%` | `越权拦截成功数 / 越权请求总数` | 日 | n8n + 业务网关日志 | Workflow Owner |
| KPI-07 | 回滚恢复时间（RTO） | `< 15 分钟` | `恢复完成时间 - 回滚触发时间` | 每次演练 | Runbook 记录 | Platform Owner |

要求：每个 KPI 必须在 Grafana 或 Langfuse 有固定面板，并能追溯到原始查询语句。

## 4. 每 Sprint 必过门禁

1. 所有变更必须 PR 合并，禁止长期手工改集群。
2. `deploy-repo-gate` 与 `scripts/verify.sh` 必须通过。
3. 安全门禁必须通过：Secret 扫描、依赖漏洞扫描、IaC 配置扫描（高危阻断合并）。
4. `pgvector` 门禁按路径条件触发：仅当 PR 变更匹配 `apps/ljwx-dify/**`、`apps/n8n/**`、`config/dify/**`、`cluster/**postgres**` 时，必须执行 `scripts/ops/check-pgvector.sh`（必要时 `--runtime`）。
5. Argo 目标应用状态必须 `Synced/Healthy`。
6. 发布后必须更新 evidence（smoke 与指标）。

## 5. S1 “四个入口”定义（必须可探测）

以 `scripts/smoke/targets.local-k3s.json` 和 `scripts/smoke/targets.orbstack-k3s-cn.json` 为准，最少包含并可访问以下 4 项：

| service | argocd_app | endpoint |
|---|---|---|
| `ljwx-website` | `ljwx-website-dev` | `http://ljwx-website.ljwx-website-dev.svc.cluster.local/health` |
| `ljwx-dify` | `ljwx-dify-dev` | `http://api.ljwx-dify-dev.svc.cluster.local:5001/health` |
| `ljwx-dify-web` | `ljwx-dify-dev` | `http://web.ljwx-dify-dev.svc.cluster.local:3000/` |
| `ljwx-chat` | `ljwx-chat-dev` | `http://ljwx-chat.ljwx-chat-dev.svc.cluster.local/` |

## 6. 本期优先级（立即执行）

| 优先级 | 事项 | Owner | 完成判定 |
|---|---|---|---|
| P0 | 5 类数据字段契约文档入库 | Data Owner | 文档合并并被 Gate 引用 |
| P0 | 5 类 n8n 模板落库并可一键安装 | Workflow Owner | 模板可导入，脚本一次复制完成 |
| P0 | 知识库同步/官网审批两条工作流跑通 | AI Owner + Business Owner | 演示链路可复现 |
| P1 | KPI 看板与日报自动推送 | Data Owner | 连续 7 天稳定输出 |
| P1 | 转人工策略与告警阈值 | Business Owner | 规则上线并有告警闭环 |

## 7. 验收命令（建议，含自动判定）

```bash
bash scripts/verify.sh

# 仅在满足第 4 节路径条件时执行
bash scripts/ops/check-pgvector.sh

# smoke target 覆盖检查（本地可先 dry-run）
python3 scripts/smoke/run_smoke.py --dry-run --targets scripts/smoke/targets.local-k3s.json

# Argo 健康自动判定：存在非 Synced/Healthy 即返回非 0
kubectl -n argocd get applications.argoproj.io -o json \
  | jq -e '.items | map(select(.status.sync.status != "Synced" or .status.health.status != "Healthy")) | length == 0'
```
