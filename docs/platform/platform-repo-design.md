# Platform Repo Design

## Purpose

`ljwx-deploy` is both:

1. the only deployment source of truth
2. the integrated platform assembly repository

## Directory Roles

| Directory | Role |
| --- | --- |
| `apps/` | deployable application manifests and overlays |
| `cluster/` | namespace and cluster baselines |
| `argocd-apps/` | ArgoCD bootstrap and application ownership |
| `release/` | queue, service maps, integrated platform versions |
| `platform/` | contracts, routing, knowledge governance, env matrix, capability registry |
| `runbooks/` | operational procedures for rollback, rebuild, republish |
| `scripts/bootstrap/` | cluster bootstrap entrypoints |
| `scripts/migrate/` | migration/export helpers |

## Change Rule

If a change affects runtime behavior but not image code, it should still be represented in this repository through:

- route config
- capability registry
- knowledge publish config
- env profile
- platform version
