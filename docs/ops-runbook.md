# Ops Runbook (Promoter + Argo + Smoke)

This runbook covers day-2 operations for the async promotion path:

`GitHub queue -> Harbor pull replication -> deploy-promoter -> ArgoCD auto-sync -> smoke -> evidence feed`

## 1) Observe deploy-promoter

```bash
# manifests
kubectl -n shared-platform get cronjob deploy-promoter

# latest job and pod
kubectl -n shared-platform get jobs --sort-by=.metadata.creationTimestamp | tail -n 5
kubectl -n shared-platform get pods -l job-name=<job-name>
kubectl -n shared-platform logs job/<job-name>
```

Expected:

- If digest is not in Harbor yet: no promotion commit, queue stays in `pending`.
- If digest exists: queue entry moves to `promoted`, `envs/dev/<svc>.yaml` updated, evidence record written.

## 2) Observe ArgoCD sync/deploy

```bash
# Application status
kubectl -n argocd get applications.argoproj.io
kubectl -n argocd get applications.argoproj.io <app-name> -o yaml | rg "sync|health|revision|image"

# workload rollout
kubectl -n <namespace> rollout status deploy/<deploy-name> --timeout=180s
kubectl -n <namespace> get pods -o wide
```

Expected:

- Application transitions to `Synced` + `Healthy`.
- New pod uses promoted image digest.

## 3) Observe smoke results

```bash
python3 scripts/smoke/run_smoke.py --dry-run
python3 scripts/evidence/collect.py --out evidence/index.json --summary evidence/summary/latest.md
```

Results are recorded in each evidence file under `tests.smoke`.

## 4) Common failures

1. Harbor digest not found:
   - Validate Harbor pull replication policy and credentials.
   - Verify manifest availability with the exact curl command in `scripts/verify.sh`.
2. Queue entry stuck in `failed`:
   - Fix source image/tag/digest.
   - Re-enqueue with a new queue `id`.
3. Argo app not healthy:
   - Check sync errors/events in `kubectl -n argocd describe application <app-name>`.
   - Fix manifest/resource issue and re-sync.
4. Smoke failed:
   - Inspect `tests.smoke.details` in evidence record.
   - Confirm endpoint DNS/service/ingress and app readiness probe behavior.

## 5) Quick checklist (commit -> pod)

1. Service repo build pushes image to GHCR.
2. Service repo enqueues release to `release/queue.yaml` (no wait for Harbor replication).
3. Harbor pull replication mirrors artifact into `app/<svc>`.
4. Promoter sees digest and writes promotion commit.
5. Argo auto-sync applies new revision.
6. Smoke writes pass/fail to evidence record.
7. Pages feed updates with latest `evidence/index.json`.
