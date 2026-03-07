# Deployment Environments

## Current Profiles

`platform/assembly/env-matrix.yaml` is the platform-level matrix for environment and cluster behavior.

| Profile | Role | Service map | Smoke targets | Argo sync | Public HTTPS | Release gate |
| --- | --- | --- | --- | --- | --- | --- |
| `local-k3s` | default dev profile | `release/services.local-k3s.yaml` | `scripts/smoke/targets.local-k3s.json` | auto-sync | Traefik + cert-manager HTTP01 | automated |
| `orbstack-k3s-cn` | alternate dev verification profile | `release/services.orbstack-k3s-cn.yaml` | `scripts/smoke/targets.orbstack-k3s-cn.json` | auto-sync | Traefik + cert-manager HTTP01 | automated |
| `prod-planned` | production release profile | `release/services.yaml` | `scripts/smoke/targets.prod-planned.json` | auto-sync after Git merge | Traefik + cert-manager HTTP01 | manual review before prod promote |

## Environment Defaults

- `dev` defaults to `local-k3s`; `orbstack-k3s-cn` is the alternate profile when mainland verification is required against the same codebase.
- `prod` defaults to `prod-planned`.
- Production keeps a manual release gate before the prod queue/promoter step, but Argo reconciliation remains automatic once the prod overlay changes land in Git.

## Rules

1. Environment differences belong in profile files, not duplicated scripts.
2. Service map, smoke targets, Argo behavior, public ingress, and release policy must be profile-driven.
3. `release/platform-version.yaml` must point to the active env profile references used during release review.
4. Queue and promoter logic remain shared; profiles only describe environment deltas and approval boundaries.

## Secrets

Secrets are still externalized and must not be stored in this repository.
This directory only records references and expected runtime contracts.
