# Service Repo Workflow Snippet (GHCR Build + Queue Enqueue)

Use this in each service repo. CI must finish without waiting for Harbor replication.

## Dev pattern (direct enqueue to `main`)

```yaml
name: build-and-enqueue-dev

on:
  push:
    branches: [main]
    tags: ["v*"]

permissions:
  contents: write
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        run: echo "tag=sha-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      - id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/<org>/<service>:${{ steps.meta.outputs.tag }}
          labels: org.opencontainers.image.revision=${{ github.sha }}

  enqueue-dev:
    runs-on: ubuntu-latest
    needs: [build]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
        with:
          repository: BrunoGaoSZ/ljwx-deploy
          token: ${{ secrets.DEPLOY_REPO_TOKEN }}
          ref: main
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --disable-pip-version-check pyyaml
      - env:
          SERVICE: <service>
          DIGEST: ${{ needs.build.outputs.digest }}
          TAG: sha-${{ github.sha }}
        run: |
          python3 - <<'PY'
          from datetime import datetime, timezone
          import yaml, pathlib
          p = pathlib.Path("release/queue.yaml")
          q = yaml.safe_load(p.read_text()) or {}
          for k in ("pending","promoted","failed","superseded"):
              q.setdefault(k, [])
          now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
          svc = __import__("os").environ["SERVICE"]
          digest = __import__("os").environ["DIGEST"]
          tag = __import__("os").environ["TAG"]
          q["pending"].append({
              "id": f"{now}-{svc}-{tag}".replace(":","").replace("+",""),
              "service": svc,
              "env": "dev",
              "source": {
                  "ghcr": f"ghcr.io/<org>/{svc}@{digest}",
                  "tag": tag,
                  "digest": digest,
              },
              "createdAt": now,
              "status": "pending",
              "attempts": 0,
              "lastError": "",
              "promotedAt": "",
              "supersededAt": "",
              "failedAt": "",
          })
          p.write_text(yaml.safe_dump(q, sort_keys=False), encoding="utf-8")
          PY
      - run: |
          git config user.name "service-ci[bot]"
          git config user.email "service-ci[bot]@users.noreply.github.com"
          git add release/queue.yaml
          git commit -m "enqueue(dev): <service> ${GITHUB_SHA::7} [skip ci]" || exit 0
          git push origin HEAD:main
```

## Demo/Prod pattern (enqueue via PR + reviewers)

1. Build and push GHCR image exactly the same way.
2. Commit queue change on branch `enqueue/<service>-<tag>`.
3. Open PR in `ljwx-deploy` targeting `main`.
4. Require reviewer approvals for demo/prod before merge.
5. Promoter remains async and still does not block service CI.
