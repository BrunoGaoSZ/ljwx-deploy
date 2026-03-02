# Harbor Pull Replication Runbook (GHCR -> Harbor)

This runbook configures Harbor pull replication from GHCR while keeping GitHub as source of truth.

## Goal

- Build pipeline pushes images to GHCR.
- Harbor pulls from GHCR by policy.
- Promoter never assumes replication timing; it checks Harbor v2 manifest availability before pinning digest.

## Setup Steps

1. In Harbor, create a registry endpoint for `ghcr.io` with robot/token credentials.
2. Create pull-based replication policy:
   - Name: `ghcr-to-harbor-ljwx`
   - Source registry: GHCR endpoint
   - Destination project: `ljwx` (and `ljwx-health` as needed)
   - Trigger mode: scheduled or event-based
   - Filter: include required repositories only
3. Enable policy and run first sync.
4. Verify each expected repository exists in Harbor.

## Verification Commands

```bash
# Replace <repo> and <tag>
curl -sSI \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  "https://harbor.omniverseai.net/v2/<repo>/manifests/<tag>"
```

Expected: `HTTP 200` and `Docker-Content-Digest` header.

## Failure Handling

- If Harbor manifest is missing, promoter keeps item pending and increments attempts.
- When attempts exceed max, entry moves to `failed` with last error message.
- Resolve replication/policy issues and re-queue with a new queue entry id.
