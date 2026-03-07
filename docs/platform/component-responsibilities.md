# Component Responsibilities

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `ljwx-chat` | UI, session presentation, channel entry, user-facing configuration | Orchestration policy, business workflows, knowledge source-of-truth |
| `OpenClaw` | Routing, tool orchestration, execution traces, fallback policy | Persistent business state, raw knowledge governance, product backend ownership |
| `GPT` | Default generation, tool-capable responses, fast general tasks | Workflow state, knowledge publishing, business truth |
| `Claude` | Long-form analysis, design reasoning, complementary fallback | Default full traffic routing, workflow state |
| `Dify` | Dataset-backed RAG consumption, agent UX where appropriate | Raw content source, core business logic, system-wide orchestration |
| `n8n` | Deterministic workflow execution, retries, notifications, approvals | Product backend, complex reasoning, knowledge governance |
| `ljwx-core-api` | Authn/authz, audit, capability gateway, business APIs | Frontend rendering, workflow editing |
| `knowledge-processor` | Collection, normalization, classification, publish/invalidate | User-facing conversation UI |
| `ljwx-deploy` | Integrated assembly, deployment structure, env overlays, runbooks | Product feature logic |

## Guardrails

1. Core business rules go to `ljwx-core-api`, not Dify or `n8n`.
2. Routing logic goes to `platform/routing/`, not `ljwx-chat`.
3. Capability ownership is explicit in `platform/assembly/capabilities.yaml`.
4. Knowledge publication is reversible and auditable.
