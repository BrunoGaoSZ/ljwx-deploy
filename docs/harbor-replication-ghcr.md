# Harbor Pull Replication (GHCR -> Harbor)

This runbook configures Harbor pull replication from GHCR while keeping GitHub as source of truth.

## Goal

- CI pushes images to GHCR.
- Harbor pulls from GHCR by replication policy.
- Promoter does not assume replication timing; it verifies Harbor manifest availability via v2 HEAD/GET before digest pinning.

## Setup

1. In Harbor, add a remote registry endpoint for `ghcr.io` using robot/token credentials.
2. Create pull replication policy:
   - Name: `ghcr-to-harbor-ljwx`
   - Source registry: GHCR endpoint
   - Destination projects: `ljwx`, `ljwx-health` (as needed)
   - Trigger: scheduled or event-based
   - Filters: only required repositories
3. Enable policy and run initial replication.
4. Verify expected repositories exist in Harbor.

## Verification

```bash
# replace <repo> and <tag>
curl -sSI \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  "https://harbor.omniverseai.net/v2/<repo>/manifests/<tag>"
```

Expected:

- HTTP status `200`
- response header `Docker-Content-Digest: sha256:...`

## Failure Behavior in Promoter

- If manifest is missing, queue item stays pending and `attempts` increments.
- After `max_attempts`, item moves to `failed` with `last_error`.
- Resolve replication policy/credentials and re-queue with a new queue id.
