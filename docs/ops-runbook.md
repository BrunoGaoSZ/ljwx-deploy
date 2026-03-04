# Ops Runbook (Promoter + Argo + Smoke)

This runbook covers day-2 operations for the async promotion path:

`GitHub queue -> Harbor pull replication -> deploy-promoter -> ArgoCD auto-sync -> smoke -> evidence feed`

## Bootstrap (GitOps-managed CronJobs)

`deploy-promoter` and `smoke-runner` are now managed by `cluster-bootstrap` from:

- `cluster/deploy-promoter-cronjob.yaml`
- `cluster/smoke-runner-cronjob.yaml`

Required secret (not committed with real values):

- `cluster/deploy-promoter-secret.example.yaml`

Cluster rule:

- same GitOps source code for local `k3s` and OrbStack `k3s`
- cluster variance only via profile files (`SERVICE_MAP_PATH`, `SMOKE_TARGETS`)

## Grafana dashboard + TLS (GitOps)

`ljwx-platform` observability dashboard and Grafana ingress certificate are managed by Argo Application:

- `cluster/ljwx-platform-observability-application.yaml`
- source path: `apps/ljwx-platform-observability/overlays/prod`

Managed resources:

- `ConfigMap/monitoring/ljwx-platform-observability-dashboard` (label `grafana_dashboard=1`)
- `Ingress/monitoring/grafnana-ingress` (host: `grafnana.lingjingwanxiang.cn`)
- cert-manager ingress-shim certificate secret: `grafnana-lingjingwanxiang-cn-tls`

Validation:

```bash
kubectl -n argocd get app ljwx-platform-observability
kubectl -n monitoring get ingress grafnana-ingress
kubectl -n monitoring get certificate grafnana-lingjingwanxiang-cn -o wide
kubectl -n monitoring get cm ljwx-platform-observability-dashboard
```

## 1) Observe deploy-promoter

```bash
# manifests
kubectl -n dev get cronjob deploy-promoter
kubectl -n dev get cronjob deploy-promoter -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'

# latest job and pod
kubectl -n dev get jobs --sort-by=.metadata.creationTimestamp | tail -n 5
kubectl -n dev get pods -l job-name=<job-name>
kubectl -n dev logs job/<job-name>
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
   - Ensure `ghcr-pull` exists in `dev`.
   - Ensure `dev/default` ServiceAccount includes `imagePullSecrets: [{name: ghcr-pull}]`.
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
