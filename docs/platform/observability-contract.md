# Observability Contract

## Goal

Route decisions, knowledge publication, and capability execution must share one audit vocabulary.

## Shared Audit Shape

The common schema is `platform/contracts/audit-event.schema.json`.

Required fields:

1. `audit_event_id`
2. `timestamp`
3. `component`
4. `event_type`
5. `trace_id`

Optional fields align cross-component evidence:

1. `route_id`
2. `capability`
3. `document_id`
4. `selected_model`
5. `fallback_reason`
6. `success`
7. `reason`
8. `details`

## Current Implementations

1. route decision: `ljwx-chat` structured logs keep `route_id`, `selected_model`, `fallback_reason`, and `decision_duration_ms`
2. knowledge publication: `ljwx-knowledge/state/<env>/audit-events.jsonl` and `metrics.json`
3. capability execution: `ljwx-core-api/state/audit/capability-events.jsonl`, `conversation-records.jsonl`, and `/metrics`

## Key Metrics

Track at minimum:

1. route decision latency
2. knowledge publish / invalidate counts
3. capability execution total and latency
4. whitelist violation total

## Verification

1. `pnpm exec vitest run src/server/services/platformRouting/index.test.ts src/server/services/openclaw/index.test.ts`
2. `uv run pytest`
3. `uv run ljwx-knowledge --deploy-root ../ljwx-deploy run --env dev`
