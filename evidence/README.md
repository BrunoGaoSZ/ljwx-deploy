# Evidence Control Plane

This directory is the Git-tracked evidence source for Bid-MVP factory promotion and smoke outcomes.

## Structure

- `evidence/records/*.json`: immutable-ish evidence records (append/update by automation).
- `evidence/schema/evidence-record.schema.json`: canonical record schema.
- `evidence/index.json`: generated feed consumed by GitHub Pages dashboard.

## Record Lifecycle

1. Promoter creates or updates a record with queue/promotion data.
2. Smoke runner appends smoke status under `tests.smoke` in the same record identity.
3. Nightly workflow validates records and regenerates `evidence/index.json`.
4. Workflow publishes dashboard and feed to `gh-pages` branch root.

## Validation + Collection

```bash
python3 scripts/evidence/validate.py
python3 scripts/evidence/collect.py --out evidence/index.json
```

## Required Branch/Pages Governance

1. Enable GitHub Pages from `gh-pages` branch root.
2. Add branch protection rule for `gh-pages`:
   - Require linear history.
   - Restrict who can push to automation only.
   - Allow only GitHub Actions bot/app identity used by workflow.
3. Keep `gh-pages` write access only through repository workflow token (`GITHUB_TOKEN`).
4. Never commit manual edits to `gh-pages`; regenerate from `main` workflow only.

## Stable URLs

- Dashboard: `https://brunogaosz.github.io/ljwx-deploy/`
- Feed: `https://brunogaosz.github.io/ljwx-deploy/evidence/index.json`
