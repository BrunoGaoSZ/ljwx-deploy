# Node Rebuild

## Goal

Rebuild a cluster node or a small cluster using Git-managed bootstrap and application baselines.

## Steps

1. prepare host
2. install k3s
3. restore pull secrets and external secrets prerequisites
4. run `scripts/bootstrap/cluster-init.sh --env dev --profile <profile> --apply`
5. verify Argo apps
6. verify ingress and smoke targets

## Exit Criteria

- Argo apps are healthy
- promoted images match overlays
- smoke checks pass
