# Capability Gateway

## Goal

`ljwx-core-api` owns the runtime-facing capability gateway for platform business APIs.
The first MVP interface is:

- request schema: `platform/contracts/capability-gateway-request.schema.json`
- response schema: `platform/contracts/tool-result.schema.json`

## Current Runtime Capabilities

The gateway currently exposes two real capabilities:

1. `customer.lookup`
2. `conversation.audit.write`

These are implemented in `ljwx-core-api` and dispatched through `tool.gateway.execute`.

## Boundary

Use `ljwx-core-api` when the capability is:

1. business-truth owned
2. latency-sensitive
3. audit-required
4. needed directly by chat or OpenClaw runtime

Use `n8n` when the capability is:

1. workflow-heavy
2. retry-oriented
3. approval or notification centric
4. not the source of business truth

## Whitelist Rule

Capability whitelist enforcement must happen before tool invocation.
The concrete runtime whitelist lives in `ljwx-core-api/config/tool_profiles.yaml`.

If a capability is blocked by profile:

1. return `403`
2. write `event_type=whitelist_violation`
3. keep `tool-result.meta.audit_event_id`

## Validation

Run:

```bash
uvx --with pyyaml --with jsonschema python scripts/platform/validate_capability_contracts.py
```
