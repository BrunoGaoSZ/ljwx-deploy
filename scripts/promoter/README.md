# Deploy Promoter (Method-1)

Promoter reads `release/queue.yaml` and auto-promotes ready releases by mutating Argo-consumed overlay files.

## Guarantees

- Per-service serialization: at most one pending entry per `service+env`.
- Older pending entries are moved to `superseded` (not failed).
- Promotion only happens after Harbor manifest HEAD/GET returns HTTP 200.
- Idempotent rerun: already-promoted items are not promoted again.
- Promotion target resolution is centralized in `release/services.yaml`.

## Main Command

```bash
# Dry run (no commit/push)
bash scripts/promoter/promote.sh --dry-run

# Normal run (token + Harbor credentials required)
DEPLOY_REPO_TOKEN=*** HARBOR_USER=*** HARBOR_PASS=*** \
  bash scripts/promoter/promote.sh
```

## Prebuilt image

The in-cluster CronJob uses a prebuilt image to avoid `apk/pip` cold start on every minute tick.

```bash
# Build locally
docker build -f scripts/promoter/Dockerfile -t ghcr.io/<owner>/ljwx-deploy-promoter:dev .

# Run locally with the container image
docker run --rm \
  -e DEPLOY_REPO_TOKEN=*** \
  -e HARBOR_USER=*** \
  -e HARBOR_PASS=*** \
  ghcr.io/<owner>/ljwx-deploy-promoter:dev --dry-run
```

`build-promoter-image` workflow publishes:

- `ghcr.io/<owner>/ljwx-deploy-promoter:sha-<12>`
- `ghcr.io/<owner>/ljwx-deploy-promoter:main` (when built from `main`)

For Kubernetes pulls from GHCR, create and bind `ghcr-pull` in `shared-platform`:

```bash
kubectl create secret docker-registry ghcr-pull \
  -n shared-platform \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl patch serviceaccount promoter -n shared-platform \
  -p '{"imagePullSecrets":[{"name":"ghcr-pull"}]}'
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

`release/services.yaml` provides `service+env -> overlay/image/app` mapping so business repos only need to enqueue minimal release metadata.
