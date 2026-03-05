# GitHub Pages Setup for Evidence Feed

## Enable Pages

1. Open repository `Settings`.
2. Go to `Pages`.
3. Under `Build and deployment`, choose:
   - Source: `Deploy from a branch`
   - Branch: `gh-pages`
   - Folder: `/ (root)`
4. Save.

## Evidence Feed URL

After first successful publish, the URLs are typically:

- Dashboard: `https://<owner>.github.io/<repo>/`
- Feed JSON: `https://<owner>.github.io/<repo>/evidence/index.json`
- Queue health: `https://<owner>.github.io/<repo>/evidence/metrics/queue-health.json`

Example for `BrunoGaoSZ/ljwx-deploy`:

- `https://brunogaosz.github.io/ljwx-deploy/`
- `https://brunogaosz.github.io/ljwx-deploy/evidence/index.json`
- `https://brunogaosz.github.io/ljwx-deploy/evidence/metrics/queue-health.json`

## Access Control Notes

- Public repo: feed is public.
- Private/internal repo: GitHub Pages visibility depends on plan/policy.
- Keep records free of secrets/internal-only endpoints.

## gh-pages Content Contract

`nightly-evidence` now publishes with an explicit branch-content contract:

- only `index.html`, `app.js`, `evidence/index.json`, `evidence/summary/latest.md`, `evidence/metrics/queue-health.json` are kept in `gh-pages`
- all other files in `gh-pages` root are deleted before each publish

This prevents deployment manifests or source files from being accidentally retained in the Pages branch.

## Source Directory Convention

- Canonical source for Pages publish is `pages/`.
- `site/` is legacy and not used by `nightly-evidence`.
- New dashboard changes must be applied in `pages/index.html` and `pages/app.js`.
