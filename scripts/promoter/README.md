# Deploy Promoter

Promotes `release/queue.yaml` pending entries into digest-pinned dev environment manifests.

## Behavior

- Reads queue state from `release/queue.yaml`.
- Keeps only newest pending item per service; older pending items are superseded.
- Checks Harbor v2 manifest availability by HEAD/GET before promotion.
- Pins `envs/dev/<service>.yaml` image to `harbor...@sha256:<digest>`.
- Writes/updates evidence records in `evidence/records/`.
- Moves entries to `promoted` or keeps retry metadata; after max attempts moves to `failed`.

## Commands

```bash
# Dry run for local verification (no network requirement)
python3 scripts/promoter/deploy_promoter.py --dry-run --skip-registry-check

# Real promotion run (requires Harbor access)
HARBOR_USERNAME=*** HARBOR_PASSWORD=*** \
python3 scripts/promoter/deploy_promoter.py
```

## Queue File Contract

`release/queue.yaml` uses a JSON-compatible YAML structure:

- `pending`: list of to-be-promoted entries.
- `promoted`: list of successful entries.
- `failed`: list of exhausted or superseded entries.

Required per `pending` entry:

- `id`
- `service`
- `environment`
- `image.repository`
- `image.tag` or `image.digest`
- `attempts`
- `max_attempts`
- `created_at`
