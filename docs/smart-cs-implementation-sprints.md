# 企业级智能客服系统实施清单（按 Sprint 执行）

更新时间：2026-03-05  
适用环境：`ljwx-website`、`ljwx-chat`、`ljwx-dify`、`n8n`、`openclaw`、`k3s`（GitOps）

## 1. 角色与责任

| 角色 | 负责人建议 | 主要责任 |
|---|---|---|
| Platform Owner | 平台/DevOps | GitOps、ArgoCD、集群与发布规范 |
| AI Owner | AI 应用负责人 | Dify Agent、RAG、模型路由、质量优化 |
| Workflow Owner | 自动化负责人 | n8n 工作流实现与运维 |
| Data Owner | 数据/BI 负责人 | 指标口径、报表、数据保留策略 |
| Business Owner | 客服/产品负责人 | FAQ、业务规则、转人工策略 |
| QA Owner | 测试负责人 | E2E、压测、安全测试、回归准入 |

## 2. Sprint 计划（可直接执行）

| Sprint | 周期 | Owner | 目标 | 关键任务 | 验收标准（DoD） |
|---|---|---|---|---|---|
| S1 基础就绪 | Week 1 | Platform Owner | 环境和发布链路稳定 | 1) 三个业务应用全部接入 GitOps 2) `infra-data`、`cluster-bootstrap` 健康 3) 镜像策略统一（GHCR→Harbor） | 1) Argo 应用全 `Synced/Healthy` 2) 四个入口 200 可用 3) PR Gate 生效 |
| S2 数据链路最小闭环 | Week 2 | AI Owner + Workflow Owner | 跑通“知识库→对话→业务→观测”最小链路 | 1) 建立 5 类数据字段契约 2) 打通 Dify↔n8n 双向调用 3) Langfuse 可追踪全链路 | 1) 10 条样例问题可回放 trace 2) 业务透传成功率 ≥ 99% 3) 无手工改集群 |
| S3 知识库与官网内容 | Week 3-4 | AI Owner + Business Owner | 建立内容生产与审批闭环 | 1) 知识库同步自动化（FAQ/文档/Notion） 2) 官网内容 PR 审批流 3) 未命中问题回流机制 | 1) 知识库命中率 ≥ 85% 2) 官网内容变更必须经 PR 3) 回滚演练通过 |
| S4 业务透传与安全 | Week 5 | Workflow Owner + QA Owner | 业务工作流生产可用 | 1) 订单查询/工单创建/人工转接标准化 2) 鉴权与归属校验 3) 限流与错误分级 | 1) 越权访问拦截率 100% 2) P95 业务响应 < 3s 3) 失败有可追踪审计 |
| S5 运营与成本治理 | Week 6-8 | Data Owner + AI Owner | 指标、成本、质量可持续优化 | 1) KPI 口径固化 2) 每日/每周报自动推送 3) 模型分层路由与成本告警 | 1) 成本日报连续 14 天稳定 2) KPI 面板可用 3) 模型路由降本目标达成 |
| S6 上线与运维固化 | Week 9-12 | Platform Owner + QA Owner | 灰度、全量、运维标准化 | 1) 灰度发布策略 2) 应急回滚与故障演练 3) 运维 Runbook 与值班流程 | 1) 可用性 ≥ 99.5% 2) 回滚演练 RTO < 15 分钟 3) 线上变更全部可审计 |

## 3. 每 Sprint 必过门禁

1. 所有变更必须 PR 合并，禁止长期手工改集群。  
2. `deploy-repo-gate` 与 `scripts/verify.sh` 必须通过。  
3. `scripts/ops/check-pgvector.sh` 必须通过（静态；必要时 `--runtime`）。  
4. Argo 目标应用状态必须 `Synced/Healthy`。  
5. 发布后必须更新 evidence（smoke 与指标）。

## 4. 本期优先级（立即执行）

| 优先级 | 事项 | Owner | 完成判定 |
|---|---|---|---|
| P0 | 5 类数据字段契约文档入库 | Data Owner | 文档合并并被 Gate 引用 |
| P0 | 5 类 n8n 模板落库并可一键安装 | Workflow Owner | 模板可导入，脚本一次复制完成 |
| P0 | 知识库同步/官网审批两条工作流跑通 | AI Owner + Business Owner | 演示链路可复现 |
| P1 | KPI 看板与日报自动推送 | Data Owner | 连续 7 天稳定输出 |
| P1 | 转人工策略与告警阈值 | Business Owner | 规则上线并有告警闭环 |

## 5. 验收命令（建议）

```bash
bash scripts/verify.sh
bash scripts/ops/check-pgvector.sh
kubectl -n argocd get applications.argoproj.io
```

