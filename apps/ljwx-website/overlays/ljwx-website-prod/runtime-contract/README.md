# ljwx-website capability contract (prod)

## Namespace baseline

- namespace: `ljwx-website-prod`
- namespace profile: `prod-default`
- registry profile: `ghcr-and-harbor`
- runtime secret profile: `none`
- image pull secrets: `ghcr-pull, regcred`
- runtime contract secrets: `none`

## Capabilities

- ghcr_pull (namespace): Bind GHCR pull secret ghcr-pull to the namespace baseline.
- harbor_pull (namespace): Bind Harbor pull secret regcred to the namespace baseline.
- runtime_app_secret (application): Standardize service-specific runtime secret as runtime-app.

## Bootstrap commands

```bash
bash scripts/ops/sync-registry-pull-secrets.sh --target-namespace ljwx-website-prod --registry-profile ghcr-and-harbor
```

## Notes

- `runtime-contract/*.secret.example.yaml` are placeholders only and must not contain real credentials.
- `cluster_bootstrap` is disabled for this entry; keep the existing cluster namespace/application manifests as the current source of truth.
- For legacy workloads, migrate deployment manifests gradually to `runtime-infra`, `runtime-llm`, and `runtime-app` instead of app-specific secret names.
