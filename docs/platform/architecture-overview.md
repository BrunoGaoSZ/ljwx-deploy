# Architecture Overview

## Goal

建立一个以客户产品为中心、可版本化、可回滚、可迁移的 AI 平台装配结构。

## Layers

| Layer | Components | Responsibility |
| --- | --- | --- |
| Product entry | `ljwx-chat`, website embeds | Conversation UI, customer-facing experience, tenant-aware entry |
| Orchestration | `OpenClaw`, routing policy | Request classification, model selection, tool orchestration, execution audit |
| Capability | `ljwx-core-api`, `n8n`, adapters | Deterministic business actions, authz, audit, external integrations |
| Knowledge | knowledge pipeline, retrieval, Dify datasets | Normalize, classify, publish, invalidate, retrieve |
| Platform | `ljwx-deploy`, ArgoCD, k3s, GitHub Actions | GitOps, overlays, release evidence, bootstrap, rollback |

## Source-of-Truth Rules

1. Deployment truth lives in `apps/`, `cluster/`, `argocd-apps/`, and `release/`.
2. Platform behavior truth lives in `platform/`.
3. Dify consumes processed knowledge; it is not the raw knowledge source.
4. `n8n` executes workflows; it is not the business system of record.

## Request Flows

### General chat

`ljwx-chat -> OpenClaw -> route policy -> GPT -> response`

### Knowledge Q&A

`ljwx-chat -> OpenClaw -> retrieval/Dify dataset -> GPT/Claude -> cited response`

### Deterministic business action

`ljwx-chat -> OpenClaw -> capability registry -> core-api/n8n -> audited result -> response`

### Multi-step request

`ljwx-chat -> OpenClaw -> plan -> retrieval + tools + business action -> summarized response`
