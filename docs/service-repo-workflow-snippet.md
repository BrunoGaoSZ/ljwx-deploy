# Service Repo Workflow Wrapper (Template-First)

先阅读：`START-HERE-GITOPS-ONBOARDING.md`（deploy 视角）和 `ljwx-workflow-templates/START-HERE-SERVICE-WORKFLOW.md`（服务仓视角）。

新项目推荐优先使用一键脚本：

`bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard-one-shot.sh --repo "$PWD" --service <service-name> --dry-run`

如果服务需要公网域名 + HTTPS，优先改为：

`bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard-one-shot.sh --repo "$PWD" --service <service-name> --service-template public-service --public-host <domain> --dry-run`

前端类服务优先改用 `public-web-service`。

如果只补服务仓 workflow，再使用：

`bash /root/codes/ljwx-workflow-templates/scripts/quick-onboard.sh --repo "$PWD" --service <service-name>`

生成的 onboarding snippet 现在优先采用 `template + 少量 override` 的 catalog 写法。
如果声明了 `public_host`，snippet 也会带上 `ingress_profile/public_host/public_path/public_service_*`，供 deploy repo 统一生成 ingress 与 TLS 配置。

该脚本生成的 `build-and-enqueue.yml` 已内置 PR Gate（`gitops-onboarding-gate`），
未接入完整 GitOps 时会直接失败并阻断合并。

Service repositories should call reusable workflows from:

`BrunoGaoSZ/ljwx-workflow-templates`

Business repos only provide required parameters and secrets.
公网入口和证书基线统一由 `ljwx-deploy` 中的 cert-manager + ingress profile 管理，不建议在服务仓自行维护第二套公网清单。

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
      image_name: <ghcr-org>/<image-repo>
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
