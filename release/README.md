# Release Queue (Method-1)

This queue drives dev auto-promotion in `ljwx-deploy`.

## Flow

1. Service repository appends a `pending` entry into `release/queue.yaml`.
2. Harbor pull replication copies GHCR artifacts into Harbor.
3. Promoter checks Harbor digest readiness.
4. If ready, promoter updates Argo-consumed overlay (`apps/*/overlays/*/kustomization.yaml`), writes evidence, and moves queue item to `promoted`.

## Superseded Semantics

- `superseded` is not an error state.
- When multiple pending entries exist for the same `service+env`, only the newest `createdAt` remains pending.
- Older pending entries are moved to `superseded` with `supersededAt` and `reason`.

## Retry Policy

- Default retry budget `N=10`.
- Non-ready Harbor digest is skipped (no forced failure on that cycle).
- Hard processing errors increment `attempts`; once attempts reach `N`, item transitions to `failed` with `failedAt` and `lastError`.

## Service Mapping

Promoter resolves deployment targets from `release/services.yaml`:

- `overlayPath`: Argo application source path file to update.
- `kustomizeImageName`: image selector in `kustomization.yaml`.
- `harborImage`: final image repository used by runtime.
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
