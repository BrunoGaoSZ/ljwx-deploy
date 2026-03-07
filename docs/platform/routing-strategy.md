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
4. selected dataset scope
5. fallback reason when triggered
6. final cited documents or chunks for retrieval-backed answers

These fields are represented by `platform/contracts/router-request.schema.json` and `platform/contracts/router-decision.schema.json`.
