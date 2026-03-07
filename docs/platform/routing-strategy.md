# Routing Strategy

## Design Split

Routing must be split into three layers:

1. `platform/routing/routes.*.yaml`
   Business-intent to route-policy mapping.
2. `platform/routing/model-catalog.yaml`
   Provider and model capability metadata.
3. `platform/assembly/capabilities.yaml`
   Tool and service dispatch registry.

This keeps strategy, model facts, and execution targets separate.

## Chat Entrypoint

`ljwx-chat` must not infer runtime routing from ad-hoc code mappings alone.
The platform entrypoint lives in `platform/routing/routes.*.yaml` under:

```yaml
entrypoints:
  ljwx_chat:
    transport: openclaw-gateway | runtime
    visible_models:
      - lingjingwanxiang:32b
```

Reviewer trace for the current path:

1. `platform/routing/routes.*.yaml`
2. `ljwx-chat/src/server/services/platformRouting/index.ts`
3. `ljwx-chat/src/app/(backend)/webapi/chat/[provider]/route.ts`
4. `ljwx-chat/src/server/modules/ModelRuntime/index.ts`

The same visible model may appear in more than one route for the same entrypoint.
`ljwx-chat` currently disambiguates by request features:

1. `enabledSearch=true` -> `knowledge_qa`
2. `plugins/tools present` -> `tool_execution`
3. otherwise -> `general_chat`

## Target Categories

| Category | Primary | Fallback | Tool orchestration |
| --- | --- | --- | --- |
| `general_chat` | GPT | Claude | no |
| `long_analysis` | Claude | GPT | no |
| `solution_design` | Claude | GPT | optional |
| `tool_execution` | GPT | Claude | yes |
| `knowledge_qa` | GPT | Claude | yes |
| `multi_step` | GPT | Claude | yes |

## Decision Evidence

Every route decision must record:

1. matched rule IDs
2. chosen provider and model
3. enabled or skipped tools
4. selected dataset scope (`dataset_scopes`)
5. fallback reason when triggered
6. final cited documents or chunks for retrieval-backed answers

These fields are represented by `platform/contracts/router-request.schema.json` and `platform/contracts/router-decision.schema.json`.
Audit vocabulary should align with `platform/contracts/audit-event.schema.json`.

For `ljwx-chat`, the minimum visible decision fields are:

1. `route_id`
2. `selected_model`
3. `fallback_reason`
4. `decision_duration_ms`

## Evidence Chain

Reviewers and operators should be able to trace one routed response through:

1. `router-request.trace_id` + `router-request.entrypoint`
2. `router-decision.trace_id` + `router-decision.route_id` + `router-decision.selected_model`
3. `tool-result.trace_id` + `tool-result.route_id` + `tool-result.tool_name`

Retrieval-backed answers should also keep `router-decision.citations`, and tool execution should keep `tool-result.meta.audit_event_id` when an audit event exists.
Route logs should include `event_type=route_decision` and `component=ljwx-chat`.

## Validation

CI and local review should run:

```bash
uvx --with pyyaml --with jsonschema python scripts/platform/validate_router_contracts.py
bash scripts/ci/check-smart-cs-contract.sh
```
