# Evidence Model

`evidence/records/*.yaml` is the source-of-truth evidence feed for promotion and verification.

## Required fields

- `evidenceId`
- `service`
- `env`
- `source.repo`
- `source.commit`
- `image.harbor`
- `deploy.deployRepoCommit`

## Optional fields

- `source.workflowRun`
- `image.ghcr`
- `deploy.argocdApp`
- `deploy.syncedAt`
- `tests.smoke`
- `tests.e2e`
- `approvals.*`

## Lifecycle

1. Queue promoter writes/updates evidence records in `evidence/records/`.
2. Validation script checks structure and required fields.
3. Collection script builds `evidence/index.json` and `evidence/summary/latest.md`.
4. Nightly workflow publishes dashboard and feed to `gh-pages` branch root.

## Example record (YAML)

```yaml
evidenceId: 2026-03-02-frontend-sha1234
service: frontend
env: dev
source:
  repo: ghcr.io/example/frontend
  commit: sha1234
  workflowRun: https://github.com/example/frontend/actions/runs/123
image:
  ghcr: ghcr.io/example/frontend@sha256:1111111111111111111111111111111111111111111111111111111111111111
  harbor: harbor.omniverseai.net/app/frontend@sha256:2222222222222222222222222222222222222222222222222222222222222222
deploy:
  deployRepoCommit: abcdef1234567890
  argocdApp: frontend-dev
  syncedAt: 2026-03-02T02:10:00Z
tests:
  smoke:
    status: pass
    url: https://github.com/example/deploy/actions/runs/456
approvals:
  releasePr: https://github.com/example/deploy/pull/789
```
