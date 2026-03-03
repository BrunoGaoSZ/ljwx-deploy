# Deploy Promoter (Method-1)

Promoter reads `release/queue.yaml` and auto-promotes ready releases by mutating Argo-consumed overlay files.

## Guarantees

- Per-service serialization: at most one pending entry per `service+env`.
- Older pending entries are moved to `superseded` (not failed).
- Promotion uses queue `source.ghcr` (standard image path) by default.
- Optional registry readiness check can be enabled with `HARBOR_URL`.
- Idempotent rerun: already-promoted items are not promoted again.
- Promotion target resolution is centralized in `release/services.yaml`.
- One codebase can target multiple clusters by switching `SERVICE_MAP_PATH`.

## Main Command

```bash
# Dry run (no commit/push)
bash scripts/promoter/promote.sh --dry-run

# Normal run (token required; registry check optional)
DEPLOY_REPO_TOKEN=*** \
  bash scripts/promoter/promote.sh

# Transparent-cache mode (skip registry blocking)
DEPLOY_REPO_TOKEN=*** SKIP_REGISTRY_CHECK=1 \
  bash scripts/promoter/promote.sh

# Strict Harbor readiness mode
DEPLOY_REPO_TOKEN=*** HARBOR_URL=https://harbor.example.com HARBOR_USER=*** HARBOR_PASS=*** \
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
- `HARBOR_URL` (optional; empty by default)
- `HARBOR_USER`, `HARBOR_PASS`
- `SKIP_REGISTRY_CHECK` (`1/true` to pass `--skip-registry-check`)
- `RETRY_MAX` (default: `10`)
- `DRY_RUN` (`1` or `0`)
- `SERVICE_MAP_PATH` (default: `release/services.yaml`)

## Queue file

`release/queue.yaml` must contain:

- `pending`
- `promoted`
- `failed`
- `superseded`

Each entry includes `id/service/env/source/*/status/attempts/timestamps` fields described in `release/README.md`.

`release/services.yaml` provides `service+env -> overlay/image/app` mapping so business repos only need to enqueue minimal release metadata.

Cluster profiles:

- local server k3s: `release/services.local-k3s.yaml`
- China mainland OrbStack k3s: `release/services.orbstack-k3s-cn.yaml`

`scripts/promoter/deploy_promoter.py` is retained only as a compatibility wrapper. Use `promote.py` as the canonical implementation.
