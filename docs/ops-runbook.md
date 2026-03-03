# Ops Runbook (Promoter + Argo + Smoke)

This runbook covers day-2 operations for the async promotion path:

`GitHub queue -> Harbor pull replication -> deploy-promoter -> ArgoCD auto-sync -> smoke -> evidence feed`

Cluster rule:

- same GitOps source code for local `k3s` and OrbStack `k3s`
- cluster variance only via profile files (`SERVICE_MAP_PATH`, `SMOKE_TARGETS`)

## 1) Observe deploy-promoter

```bash
# manifests
kubectl -n shared-platform get cronjob deploy-promoter
kubectl -n shared-platform get cronjob deploy-promoter -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'

# latest job and pod
kubectl -n shared-platform get jobs --sort-by=.metadata.creationTimestamp | tail -n 5
kubectl -n shared-platform get pods -l job-name=<job-name>
kubectl -n shared-platform logs job/<job-name>
```

Expected:

- If digest is not in Harbor yet: no promotion commit, queue stays in `pending`.
- If digest exists: queue entry moves to `promoted`, mapped Argo overlay is updated, evidence record written.
- Promoter job startup should not spend time in `apk/pip` installation (image is prebuilt).

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
2. Promoter image pull fails (`ImagePullBackOff` on GHCR):
   - Ensure `ghcr-pull` exists in `shared-platform`.
   - Ensure `promoter` ServiceAccount includes `imagePullSecrets: [{name: ghcr-pull}]`.
   - Recreate stuck jobs after secret/SA fix.
3. Queue entry stuck in `failed`:
   - Fix source image/tag/digest.
   - Re-enqueue with a new queue `id`.
4. Argo app not healthy:
   - Check sync errors/events in `kubectl -n argocd describe application <app-name>`.
   - Fix manifest/resource issue and re-sync.
5. Smoke failed:
   - Inspect `tests.smoke.details` in evidence record.
   - Confirm endpoint DNS/service/ingress and app readiness probe behavior.

## 5) Quick checklist (commit -> pod)

1. Service repo build pushes image to GHCR.
2. Service repo enqueues release to `release/queue.yaml` (no wait for Harbor replication).
3. Promoter cluster profile selects mapping:
   - local `k3s`: `release/services.local-k3s.yaml`
   - OrbStack `k3s`: `release/services.orbstack-k3s-cn.yaml`
4. Harbor pull replication mirrors artifact into `app/<svc>`.
5. Promoter sees digest and writes promotion commit.
6. Argo auto-sync applies new revision.
7. Smoke (profile-based targets) writes pass/fail to evidence record.
8. Pages feed updates with latest `evidence/index.json`.
