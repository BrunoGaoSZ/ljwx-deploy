# ljwx-stock-agent capability contract (dev)

## Namespace baseline

- namespace: `ljwx-stock`
- namespace profile: `dev-default`
- registry profile: `ghcr-and-harbor`
- runtime secret profile: `none`
- image pull secrets: `ghcr-pull, regcred`
- runtime contract secrets: `none`

## Capabilities

- ghcr_pull (namespace): Bind GHCR pull secret ghcr-pull to the namespace baseline.
- harbor_pull (namespace): Bind Harbor pull secret regcred to the namespace baseline.

## Public endpoint

- ingress profile: `traefik-letsencrypt-public`
- host: `https://stock-agent.lingjingwanxiang.cn`
- ingress class: `traefik`
- cluster issuer: `dnspod-letsencrypt`
- tls secret: `stock-agent-lingjingwanxiang-cn-tls`
- ingress artifact generation: `enabled`

## Bootstrap commands

```bash
bash scripts/ops/sync-registry-pull-secrets.sh --target-namespace ljwx-stock --registry-profile ghcr-and-harbor
```

## Notes

- `runtime-contract/*.secret.example.yaml` are placeholders only and must not contain real credentials.
- `cluster_bootstrap` is disabled for this entry; keep the existing cluster namespace/application manifests as the current source of truth.
- For legacy workloads, migrate deployment manifests gradually to `runtime-infra`, `runtime-llm`, and `runtime-app` instead of app-specific secret names.
