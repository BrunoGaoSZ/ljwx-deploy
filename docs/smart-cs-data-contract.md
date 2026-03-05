# Smart CS Data Contract（5 类数据统一契约）

更新时间：2026-03-05
适用范围：`ljwx-website`、`ljwx-chat`、`ljwx-dify`、`n8n`、`openclaw`、`langfuse`、`grafana`

## 1. 目标

本契约用于统一智能客服系统 5 类数据的字段、口径、来源与责任人，确保：

1. 同一指标在不同系统计算结果一致。
2. 数据链路可追踪（traceable）且可审计（auditable）。
3. GitOps 发布与运营看板使用同一套数据定义。

## 2. 域与主键

| 域 | Domain Key | 主键 | 写入方 | 读取方 |
|---|---|---|---|---|
| 知识库数据 | `knowledge_base` | `document_id` + `chunk_id` | Dify / n8n | Dify RAG / 管理后台 |
| 对话数据 | `conversation` | `conversation_id` + `message_id` | Dify / n8n / OpenClaw | Dify / Langfuse / BI |
| 业务数据 | `business_action` | `request_id` | n8n | Dify / 业务系统 |
| 运营数据 | `ops_metric` | `metric_id` + `ts_bucket` | Langfuse / Prometheus / n8n | Grafana / 报表 |
| 官网内容数据 | `website_content` | `content_id` + `version` | GitHub Actions / 人工 | 官网前端 / 审批流 |

## 3. 字段定义

### 3.1 知识库数据（knowledge_base）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `document_id` | string | 是 | 文档唯一标识 |
| `source_type` | enum | 是 | `docs`/`faq`/`notion`/`changelog`/`ticket` |
| `source_uri` | string | 是 | 来源地址或仓库路径 |
| `chunk_id` | string | 是 | 分段唯一标识 |
| `chunk_text` | string | 是 | 分段文本 |
| `embedding_model` | string | 是 | 向量模型名 |
| `updated_at` | datetime | 是 | 更新时间（UTC） |

### 3.2 对话数据（conversation）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `conversation_id` | string | 是 | 会话 ID |
| `message_id` | string | 是 | 消息 ID |
| `channel` | enum | 是 | `web`/`whatsapp`/`feishu`/`telegram`/`slack` |
| `user_id` | string | 否 | 用户标识（可脱敏） |
| `query` | string | 是 | 用户输入 |
| `answer` | string | 是 | AI 回复 |
| `intent` | string | 否 | 意图分类 |
| `model_used` | string | 否 | 实际调用模型 |
| `token_input` | integer | 否 | 输入 token |
| `token_output` | integer | 否 | 输出 token |
| `latency_ms` | integer | 否 | 端到端延迟 |
| `handoff_triggered` | boolean | 是 | 是否转人工 |
| `created_at` | datetime | 是 | 创建时间（UTC） |

### 3.3 业务数据（business_action）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request_id` | string | 是 | 业务请求唯一 ID |
| `action_type` | enum | 是 | `order_query`/`ticket_create`/`handoff` |
| `system_name` | enum | 是 | `erp`/`crm`/`ticket` |
| `user_id` | string | 是 | 业务主体用户 |
| `resource_id` | string | 否 | 如 `order_id`、`ticket_id` |
| `status_code` | integer | 是 | 外部系统响应码 |
| `success` | boolean | 是 | 是否成功 |
| `error_code` | string | 否 | 失败错误码 |
| `duration_ms` | integer | 是 | 调用耗时 |
| `created_at` | datetime | 是 | 创建时间（UTC） |

### 3.4 运营数据（ops_metric）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `metric_id` | string | 是 | 指标 ID（如 `KPI-01`） |
| `metric_name` | string | 是 | 指标名称 |
| `metric_value` | number | 是 | 指标值 |
| `dimension` | object | 否 | 维度（渠道/模型/环境） |
| `window` | enum | 是 | `day`/`week`/`month` |
| `source_system` | string | 是 | `langfuse`/`prometheus`/`n8n` |
| `ts_bucket` | datetime | 是 | 统计时间桶 |

### 3.5 官网内容数据（website_content）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `content_id` | string | 是 | 内容唯一 ID |
| `content_type` | enum | 是 | `faq`/`help`/`changelog` |
| `title` | string | 是 | 标题 |
| `body_markdown` | string | 是 | 正文 |
| `source_ref` | string | 否 | 来源引用 |
| `generated_by` | enum | 是 | `human`/`ai` |
| `review_status` | enum | 是 | `draft`/`reviewing`/`approved`/`rejected` |
| `pr_number` | integer | 否 | 对应 PR 号 |
| `version` | string | 是 | 版本号 |
| `updated_at` | datetime | 是 | 更新时间（UTC） |

## 4. KPI 与指标映射

| KPI ID | 依赖域 | 关键字段 |
|---|---|---|
| `KPI-01` 可用性 | `ops_metric` | `metric_value`, `window`, `source_system` |
| `KPI-02` 首次响应 P95 | `conversation` | `latency_ms`, `channel`, `created_at` |
| `KPI-03` 业务透传成功率 | `business_action` | `success`, `action_type`, `created_at` |
| `KPI-04` 知识库命中率 | `knowledge_base` + `conversation` | `chunk_id`, `intent`, `message_id` |
| `KPI-05` AI 自主解决率 | `conversation` | `handoff_triggered`, `conversation_id` |
| `KPI-06` 越权拦截率 | `business_action` | `action_type`, `error_code`, `success` |
| `KPI-07` 回滚 RTO | `ops_metric` + Runbook | `metric_value`, `ts_bucket` |

## 5. 数据治理要求

1. 生产环境禁止 mock 数据写入指标链路。
2. 所有事件必须包含 UTC 时间戳。
3. 含用户标识字段必须遵循最小化原则，必要时脱敏。
4. 所有 schema 变更必须通过 PR 审核并在本文件记录变更。

## 6. 变更记录

- 2026-03-05：初版建立，覆盖 5 类数据域与 KPI 映射。
