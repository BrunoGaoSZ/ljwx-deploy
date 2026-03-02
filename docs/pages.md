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

Example for `BrunoGaoSZ/ljwx-deploy`:

- `https://brunogaosz.github.io/ljwx-deploy/`
- `https://brunogaosz.github.io/ljwx-deploy/evidence/index.json`

## Access Control Notes

- Public repo: feed is public.
- Private/internal repo: GitHub Pages visibility depends on plan/policy.
- Keep records free of secrets/internal-only endpoints.
