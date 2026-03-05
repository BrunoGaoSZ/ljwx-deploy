# Ops Runbook (Promoter + Argo + Smoke)

This runbook covers day-2 operations for the async promotion path:

`GitHub queue -> 本地 Harbor 就绪 -> deploy-promoter(dev) -> ArgoCD(dev) -> smoke -> prod enqueue -> 生产 Harbor 就绪 -> deploy-promoter-prod -> ArgoCD(prod) -> evidence feed`

## Bootstrap (GitOps-managed CronJobs)

`deploy-promoter`、`deploy-promoter-prod` and `smoke-runner` are now managed by `cluster-bootstrap` from:

- `cluster/deploy-promoter-cronjob.yaml`
- `cluster/deploy-promoter-prod-cronjob.yaml`
- `cluster/smoke-runner-cronjob.yaml`

Required secret (not committed with real values):

- `cluster/deploy-promoter-secret.example.yaml`
- 推荐使用 `deploy_repo_token`（最小权限）替代通用 `github_token`

Cluster rule:

- same GitOps source code for local `k3s` and OrbStack `k3s`
- cluster variance only via profile files (`SERVICE_MAP_PATH`, `SMOKE_TARGETS`) and env gate (`ENV_ALLOWLIST`)

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
kubectl -n monitoring get certificate grafnana-lingjingwanxiang-cn-tls -o wide
kubectl -n monitoring get cm ljwx-platform-observability-dashboard
```

## 1) Observe deploy-promoter (dev/prod 两阶段)

```bash
# manifests
kubectl -n dev get cronjob deploy-promoter
kubectl -n dev get cronjob deploy-promoter-prod
kubectl -n dev get cronjob deploy-promoter -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n dev get cronjob deploy-promoter-prod -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env}{"\n"}' | rg "ENV_ALLOWLIST|HARBOR_URL"

# latest job and pod
kubectl -n dev get jobs --sort-by=.metadata.creationTimestamp | tail -n 5
kubectl -n dev get pods -l job-name=<job-name>
kubectl -n dev logs job/<job-name>
```

Expected:

- `deploy-promoter` 只处理 `ENV_ALLOWLIST=dev,demo`，并等待本地 Harbor digest 就绪。
- `deploy-promoter-prod` 只处理 `ENV_ALLOWLIST=prod`，并等待生产 Harbor digest 就绪。
- If digest is not ready in the target Harbor: queue stays in `pending`.
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
Queue health metrics are generated at `evidence/metrics/queue-health.json`.
When `--auto-tag-local-harbor` is enabled, smoke pass will call Harbor API to add
`prod-*` tag to local Harbor artifact.  
When `--auto-enqueue-prod` is enabled, only tag-success entries will append `env=prod` pending entries.

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

## 5) Quick checklist (commit -> dev -> prod)

1. Service repo build pushes image to GHCR.
2. Service repo enqueues `env=dev` release to `release/queue.yaml` (no wait for Harbor replication).
3. Local Harbor replication pulls artifact from GHCR.
4. `deploy-promoter` (dev allowlist) waits local Harbor digest ready, then promotes dev overlay.
5. Argo auto-sync applies dev revision.
6. Smoke (profile-based targets) writes pass/fail to evidence record.
7. Smoke runner auto-tags local Harbor artifact with `prod-*` (Harbor API).
8. Smoke runner auto-enqueues `env=prod` pending entry when tag succeeds.
9. Production Harbor replication (filter `prod-*`) receives artifact from local Harbor.
10. `deploy-promoter-prod` (prod allowlist) waits production Harbor digest ready, then promotes prod overlay.
11. Argo auto-sync applies prod revision.
12. Pages feed updates with latest `evidence/index.json`.
13. Queue health feed updates at `evidence/metrics/queue-health.json`.

Promoter profile notes:
   - local `k3s`: `release/services.local-k3s.yaml`
   - OrbStack `k3s`: `release/services.orbstack-k3s-cn.yaml`
