# Smoke Runner

Runs post-deploy smoke checks and writes results to YAML evidence records.

## Logic

1. Resolve `queueId` for each target (prefer target `queue_id`, fallback to latest promoted entry in `release/queue.yaml`).
2. Find evidence record by `service/environment/queueId` from `evidence/records/*.yaml` (prefer `smoke=pending`).
3. Wait for Argo app `Synced + Healthy` (if Argo credentials/app name are configured).
4. Check service endpoint readiness (`HTTP 2xx/3xx`).
5. Update evidence record `tests.smoke.status`, `tests.smoke.checkedAt`, `tests.smoke.details`.

## Queue precision

To pin smoke to a specific promotion:

```json
{
  "service": "frontend",
  "environment": "dev",
  "queue_id": "20260305T010000Z-frontend-sha-abc1234",
  "argocd_app": "frontend-dev",
  "endpoint": "http://frontend.dev.svc.cluster.local/"
}
```

Without `queue_id`, runner auto-resolves latest promoted queue entry for `service/environment`.

## Usage

```bash
# dry run (still performs checks, does not write files)
python3 scripts/smoke/run_smoke.py --dry-run --queue release/queue.yaml

# CI structural check mode (do not fail pipeline on endpoint/network reachability)
python3 scripts/smoke/run_smoke.py --dry-run --allow-failures --queue release/queue.yaml

# normal run
ARGOCD_SERVER=https://argocd.example.com \
ARGOCD_TOKEN=*** \
python3 scripts/smoke/run_smoke.py --queue release/queue.yaml
```

## Cluster profiles

Use target files instead of forking smoke logic:

- local server k3s: `scripts/smoke/targets.local-k3s.json`
- China mainland OrbStack k3s: `scripts/smoke/targets.orbstack-k3s-cn.json`

Example:

```bash
python3 scripts/smoke/run_smoke.py --targets scripts/smoke/targets.orbstack-k3s-cn.json --queue release/queue.yaml
```
