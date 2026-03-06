# ljwx-chat capability contract (dev)

## Namespace baseline

- namespace: `ljwx-chat-dev`
- namespace profile: `dev-default`
- registry profile: `ghcr-and-harbor`
- runtime secret profile: `app-runtime`
- image pull secrets: `ghcr-pull, regcred`
- runtime contract secrets: `runtime-app`

## Capabilities

- ghcr_pull (namespace): Bind GHCR pull secret ghcr-pull to the namespace baseline.
- harbor_pull (namespace): Bind Harbor pull secret regcred to the namespace baseline.
- runtime_app_secret (application): Standardize service-specific runtime secret as runtime-app.

## Bootstrap commands

```bash
bash scripts/ops/sync-registry-pull-secrets.sh --target-namespace ljwx-chat-dev --registry-profile ghcr-and-harbor
kubectl create secret generic runtime-app -n ljwx-chat-dev --from-literal=EXAMPLE_KEY='replace-me'
```

## Notes

- `runtime-contract/*.secret.example.yaml` are placeholders only and must not contain real credentials.
- Namespace baseline is generated into `cluster/namespace-<namespace>.yaml` and should remain the source of truth.
- For legacy workloads, migrate deployment manifests gradually to `runtime-infra`, `runtime-llm`, and `runtime-app` instead of app-specific secret names.
