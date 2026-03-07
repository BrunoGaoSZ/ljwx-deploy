# ljwx-platform capability contract (prod)

## Namespace baseline

- namespace: `ljwx-platform`
- namespace profile: `prod-default`
- registry profile: `harbor-only`
- runtime secret profile: `app-runtime`
- image pull secrets: `regcred`
- runtime contract secrets: `runtime-app`

## Capabilities

- ghcr_pull (namespace): Bind GHCR pull secret ghcr-pull to the namespace baseline.
- harbor_pull (namespace): Bind Harbor pull secret regcred to the namespace baseline.
- runtime_app_secret (application): Standardize service-specific runtime secret as runtime-app.

## Bootstrap commands

```bash
bash scripts/ops/sync-registry-pull-secrets.sh --target-namespace ljwx-platform --registry-profile harbor-only
kubectl create secret generic runtime-app -n ljwx-platform --from-literal=EXAMPLE_KEY='replace-me'
```

## Notes

- `runtime-contract/*.secret.example.yaml` are placeholders only and must not contain real credentials.
- Namespace baseline is generated into `cluster-prod/namespace-<namespace>.yaml` and should remain the source of truth.
- For legacy workloads, migrate deployment manifests gradually to `runtime-infra`, `runtime-llm`, and `runtime-app` instead of app-specific secret names.
