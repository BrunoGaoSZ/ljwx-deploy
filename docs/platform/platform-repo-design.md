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

## Review Entry Points

| File | Role |
| --- | --- |
| `release/platform-version.yaml` | composite review baseline for active platform services and cross-repo config references |
| `platform/assembly/env-matrix.yaml` | environment delta truth source for service maps, smoke targets, Argo behavior, HTTPS, and approval gates |

## Change Rule

If a change affects runtime behavior but not image code, it should still be represented in this repository through:

- route config
- capability registry
- knowledge publish config
- env profile
- platform version

Reviewers should be able to start from `release/platform-version.yaml`, follow
the referenced env profile in `platform/assembly/env-matrix.yaml`, and then walk
to the concrete overlay or cluster manifest without oral context.
