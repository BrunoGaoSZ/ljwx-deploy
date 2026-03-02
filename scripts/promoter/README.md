# Deploy Promoter (Method-1)

Promoter reads `release/queue.yaml` and auto-promotes ready dev releases.

## Guarantees

- Per-service serialization: at most one pending entry per `service+env`.
- Older pending entries are moved to `superseded` (not failed).
- Promotion only happens after Harbor manifest HEAD/GET returns HTTP 200.
- Idempotent rerun: already-promoted items are not promoted again.

## Main Command

```bash
# Dry run (no commit/push)
bash scripts/promoter/promote.sh --dry-run

# Normal run (token + Harbor credentials required)
DEPLOY_REPO_TOKEN=*** HARBOR_USER=*** HARBOR_PASS=*** \
  bash scripts/promoter/promote.sh
```

## Environment variables

- `DEPLOY_REPO_URL` (default: `https://github.com/BrunoGaoSZ/ljwx-deploy.git`)
- `DEPLOY_REPO_TOKEN` (required unless using `--local-repo-dir`)
- `HARBOR_URL` (default: `https://harbor.omniverseai.net`)
- `HARBOR_USER`, `HARBOR_PASS`
- `RETRY_MAX` (default: `10`)
- `DRY_RUN` (`1` or `0`)

## Queue file

`release/queue.yaml` must contain:

- `pending`
- `promoted`
- `failed`
- `superseded`

Each entry includes `id/service/env/source/*/status/attempts/timestamps` fields described in `release/README.md`.
