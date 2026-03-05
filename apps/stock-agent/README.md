# stock-agent GitOps onboarding

`stock-agent` is deployed independently and managed by Argo CD from:

- `apps/stock-agent/overlays/ljwx-stock`
- Argo app: `stock-agent-dev`
- Namespace: `ljwx-stock`

## Required runtime secret

`Deployment/stock-agent` expects Secret `stock-agent-secret` with keys:

- `API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_BASE_URL`

You can create/update it from `ljwx-stock/.env` (Claude proxy settings) with:

```bash
cd /root/codes/ljwx-stock
set -a
source .env
set +a

kubectl -n ljwx-stock create secret generic stock-agent-secret \
  --from-literal=API_KEY="CHANGE_ME_API_KEY" \
  --from-literal=ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN}" \
  --from-literal=ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Reference template: `apps/stock-agent/base/secret-stock-agent.example.yaml`.
