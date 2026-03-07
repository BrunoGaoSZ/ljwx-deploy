# Release Queue (Method-1)

This queue drives dev auto-promotion and prod rollout handoff in `ljwx-deploy`.

## Flow

1. Service repository appends a `pending` entry into `release/queue.yaml`.
2. Local Harbor replication / proxy cache prepares upstream images from GHCR.
3. Dev promoter promotes using standard image repository from `source.ghcr` by default and, when enabled, waits for local Harbor digest readiness.
4. Dev promoter updates Argo-consumed dev overlay (`apps/*/overlays/*/kustomization.yaml`), writes evidence, and moves queue item to `promoted`.
5. Smoke may auto-tag the local Harbor artifact as `prod-*` and enqueue a new `env=prod` entry.
6. Production Harbor (`https://harbor.omniverseai.net/`) receives the production-ready artifact from local Harbor replication.
7. Prod promoter waits for production Harbor digest readiness, updates prod overlay, and lets production ArgoCD detect and deploy the change.

## Superseded Semantics

- `superseded` is not an error state.
- When multiple pending entries exist for the same `service+env`, only the newest `createdAt` remains pending.
- Older pending entries are moved to `superseded` with `supersededAt` and `reason`.

## Retry Policy

- Default retry budget `N=10`.
- If registry readiness check is enabled and digest is not ready, entry is skipped for this cycle (no forced failure).
- Hard processing errors increment `attempts`; once attempts reach `N`, item transitions to `failed` with `failedAt` and `lastError`.

## Service Mapping

Promoter resolves deployment targets from `release/services.yaml`:

- `overlayPath`: Argo application source path file to update.
- `kustomizeImageName`: image selector in `kustomization.yaml`.
- `harborImage`: optional legacy/fallback image repository (used when queue `source.ghcr` is absent).
- `deployImage`: optional explicit runtime repository override.
- `argocdApp`: app name written into evidence records.

This mapping is the decoupling boundary. Business repos only enqueue queue entries; they do not need deploy path details.

## Dual-k3s Same-code Rule

- Use the same queue/evidence/promoter code for both clusters.
- Switch only mapping profile by environment variable:
  - local server k3s: `SERVICE_MAP_PATH=release/services.local-k3s.yaml`
  - China mainland OrbStack k3s: `SERVICE_MAP_PATH=release/services.orbstack-k3s-cn.yaml`
- Do not fork promoter logic or queue schema by cluster.

## Queue Entry Schema

```yaml
id: "20260302T020000Z-frontend-sha-abc1234"
service: "frontend"
env: "dev"
source:
  ghcr: "ghcr.io/org/frontend@sha256:..."
  tag: "sha-abc1234"
  digest: "sha256:..."
createdAt: "2026-03-02T02:00:00Z"
status: "pending"
attempts: 0
lastError: ""
promotedAt: ""
supersededAt: ""
failedAt: ""
```
