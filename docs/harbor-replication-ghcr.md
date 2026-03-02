# Harbor Pull Replication Runbook (GHCR -> Harbor `app`)

Use Harbor 2.x Pull Replication. CI must only push to GHCR and must not wait for replication.

## Target behavior

1. Service CI pushes `ghcr.io/<org>/<svc>:sha-*` or `v*`.
2. Harbor policy pulls into local project `app`.
3. Promoter checks Harbor v2 manifest API.
4. Only when manifest exists, promoter updates deploy repo.

## Harbor UI steps

1. `Administration -> Registries -> New Endpoint`
   - Provider: `GitHub Container Registry`
   - URL: `https://ghcr.io`
   - Credential: GHCR PAT/robot with pull scope
2. `Administration -> Replications -> New Replication Rule`
   - Name: `ghcr-to-app`
   - Direction: `Pull-based`
   - Source registry: the GHCR endpoint above
   - Destination namespace/project: `app`
   - Trigger mode: `Scheduled`
   - Cron: `*/1 * * * *` (every 1 minute)
   - Resource filters:
     - Repository: only required service repos
     - Tag: `sha-*`
     - Tag: `v*`
3. Enable rule and execute once for bootstrap.

## Verification commands

```bash
# by digest (preferred by promoter)
curl -u "${HARBOR_USER}:${HARBOR_PASS}" -I \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "https://harbor.omniverseai.net/v2/app/<svc>/manifests/sha256:<digest>"

# by tag (manual verification)
curl -u "${HARBOR_USER}:${HARBOR_PASS}" -I \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "https://harbor.omniverseai.net/v2/app/<svc>/manifests/sha-<shortsha>"
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
