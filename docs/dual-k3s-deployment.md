# Dual-k3s Deployment (Single Codebase)

This repository deploys to two development clusters with the same GitOps source:

- local server `k3s`
- China mainland development server `OrbStack k3s`

## Rule

- Keep one shared codebase and shared automation.
- Encode cluster differences only through profile files and runtime parameters.
- Do not fork scripts/workflows by cluster.

## Profile Files

- Promoter service mapping:
  - `release/services.local-k3s.yaml`
  - `release/services.orbstack-k3s-cn.yaml`
- Smoke targets:
  - `scripts/smoke/targets.local-k3s.json`
  - `scripts/smoke/targets.orbstack-k3s-cn.json`

## Runtime Parameters

- `SERVICE_MAP_PATH`: selects promoter mapping profile.
- `SMOKE_TARGETS`: selects smoke target profile.

Example:

```bash
SERVICE_MAP_PATH=release/services.orbstack-k3s-cn.yaml \
bash scripts/promoter/promote.sh --dry-run

SMOKE_TARGETS=scripts/smoke/targets.orbstack-k3s-cn.json \
uvx --with pyyaml --with jsonschema python scripts/smoke/run_smoke.py --dry-run --targets "${SMOKE_TARGETS}"
```
