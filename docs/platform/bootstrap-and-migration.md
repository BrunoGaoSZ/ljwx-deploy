# Bootstrap And Migration

## Bootstrap Goal

Bring up a new server or cluster by replaying Git-managed baselines instead of rebuilding state manually.

## Bootstrap Sequence

1. prepare host and k3s
2. prepare registry pull and secret management prerequisites
3. run `scripts/bootstrap/cluster-init.sh`
4. apply Argo bootstrap apps
5. sync app overlays
6. run smoke and evidence checks

## Migration Goal

Migrate workloads or contracts from legacy directories into Git-managed platform structure without changing the runtime truth boundary.

## Migration Rule

When moving legacy assets:

1. export contracts and examples first
2. add platform config references
3. validate Argo and smoke targets
4. only then retire legacy entrypoints
