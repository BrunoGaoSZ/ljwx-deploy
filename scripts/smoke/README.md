# Smoke Runner

Runs post-deploy smoke checks and writes results to YAML evidence records.

## Logic

1. Find latest promoted record for each target service/environment from `evidence/records/*.yaml`.
2. Wait for Argo app `Synced + Healthy` (if Argo credentials/app name are configured).
3. Check service endpoint readiness (`HTTP 2xx/3xx`).
4. Update evidence record `tests.smoke.status`, `tests.smoke.checkedAt`, `tests.smoke.details`.

## Usage

```bash
# dry run (still performs checks, does not write files)
python3 scripts/smoke/run_smoke.py --dry-run

# normal run
ARGOCD_SERVER=https://argocd.example.com \
ARGOCD_TOKEN=*** \
python3 scripts/smoke/run_smoke.py
```
