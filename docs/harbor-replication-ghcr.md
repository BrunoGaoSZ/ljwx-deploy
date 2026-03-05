# Harbor Pull Replication Runbook (GHCR -> Harbor `ljwx`)

Use Harbor 2.x Pull Replication. CI must only push to GHCR and must not wait for replication.

## Target behavior

1. Service CI pushes `ghcr.io/<org>/<svc>:sha-*` or `v*`.
2. Local Harbor (`harbor.eu.lingjingwanxiang.cn`) pulls from GHCR.
3. Dev promoter waits local Harbor digest readiness, then deploys dev/demo.
4. Smoke passes, then auto-tags local Harbor artifact as `prod-*` (Harbor API).
5. Smoke runner auto-enqueues `env=prod`.
6. Production Harbor (`harbor.omniverseai.net`) receives artifact from local Harbor (filter `prod-*`).
7. Prod promoter (running on production cluster) waits production Harbor digest readiness, then deploys prod.
8. Production registry pull secret sync (`cluster-prod/registry-pull-secret-sync-cronjob.yaml`) keeps target namespaces imagePull secrets up to date.

Production Argo bootstrap manifest:

- `argocd-apps/02-cluster-prod-bootstrap.yaml`

## Harbor UI steps

1. `Administration -> Registries -> New Endpoint`
   - Provider: `GitHub Container Registry`
   - URL: `https://ghcr.io`
   - Credential: GHCR PAT/robot with pull scope
2. `Administration -> Replications -> New Replication Rule`
   - Name: `ghcr-to-app`
   - Direction: `Pull-based`
   - Source registry: the GHCR endpoint above
   - Destination namespace/project: `ljwx`
   - Trigger mode: `Scheduled`
   - Cron: `*/1 * * * *` (every 1 minute)
   - Resource filters:
     - Repository: only required service repos
     - Tag: `sha-*`
     - Tag: `v*`
3. Enable rule and execute once for bootstrap.

## Recommended 2-stage replication split

1. GHCR -> local Harbor (`harbor.eu.lingjingwanxiang.cn/ljwx`)
   - keep existing rule for `sha-*` / `v*`
2. local Harbor -> production Harbor (`harbor.omniverseai.net/ljwx`)
   - recommended filter: only production-ready tags (for example `prod-*`)
   - trigger mode: event-based + scheduled fallback
   - this avoids syncing every dev candidate to production Harbor

## Verification commands

```bash
# by digest (preferred by promoter)
curl -u "${HARBOR_USER}:${HARBOR_PASS}" -I \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "https://<your-harbor-domain>/v2/ljwx/<svc>/manifests/sha256:<digest>"

# by tag (manual verification)
curl -u "${HARBOR_USER}:${HARBOR_PASS}" -I \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "https://<your-harbor-domain>/v2/ljwx/<svc>/manifests/sha-<shortsha>"
```

Expected:

- HTTP `200`
- `Docker-Content-Digest: sha256:...`

## Troubleshooting

1. `401/403` from Harbor:
   - Check robot user/password in promoter secret.
   - Validate Harbor project permission for `app/<svc>`.
2. `404` manifest:
   - Replication not finished yet, source tag missing, or filter mismatch.
   - Verify rule execution history in Harbor UI.
3. Queue stuck in `pending`:
   - Confirm digest in queue entry equals GHCR build digest.
   - Run verification curl manually.
4. Queue moved to `failed`:
   - Fix root cause, then re-enqueue with a new `id`.
5. Pod image pull secret error (`FailedToRetrieveImagePullSecret` / `ImagePullBackOff`):
   - Ensure target namespace has label `registry-sync.ljwx.io/enabled=true`.
   - Check sync job status/log:
     - `kubectl -n dev get cronjob registry-pull-secret-sync`
     - `kubectl -n dev logs job/<registry-pull-secret-sync-job-name>`
   - Verify synced secret:
     - `kubectl -n <ns> get secret harbor-registry ghcr-pull regcred`
