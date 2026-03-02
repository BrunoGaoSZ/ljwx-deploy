# Service Repo Workflow Wrapper (Template-First)

Service repositories should call reusable workflows from:

`BrunoGaoSZ/ljwx-workflow-templates`

Business repos only provide required parameters and secrets.

## Dev wrapper (direct enqueue)

```yaml
name: build-and-enqueue-dev

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "replace with lint/test"

  build:
    if: github.event_name != 'pull_request'
    needs: [test]
    uses: BrunoGaoSZ/ljwx-workflow-templates/.github/workflows/build-ghcr.yml@main
    with:
      image_name: <service>
      context: .
      dockerfile: Dockerfile
      platforms: linux/amd64,linux/arm64
      push_latest: true
    secrets: inherit

  enqueue-dev:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    needs: [build]
    uses: BrunoGaoSZ/ljwx-workflow-templates/.github/workflows/enqueue-release.yml@main
    with:
      service: <service>
      env: dev
      ghcr_ref: ${{ needs.build.outputs.ghcr_ref }}
      tag: ${{ needs.build.outputs.tag }}
      deploy_repo: BrunoGaoSZ/ljwx-deploy
      deploy_ref: main
      open_pr: false
    secrets:
      deploy_repo_token: ${{ secrets.DEPLOY_REPO_TOKEN }}
```

## Demo/Prod wrapper (PR enqueue)

Use the same build job and set:

- `env: demo` or `env: prod`
- `open_pr: true`

This keeps reviewer approval in deploy repo while still keeping service CI independent from Harbor replication timing.
