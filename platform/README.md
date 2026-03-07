# Platform Config

This directory stores platform-level assembly artifacts that are not application source code.
`platform/assembly/env-matrix.yaml` is the environment-delta truth source, and
`release/platform-version.yaml` is the integrated review entrypoint that points
back to these files.

- `assembly/`: environment matrix and capability registry
- `contracts/`: request, decision, audit, and knowledge contracts
- `routing/`: route policies and model catalog
- `knowledge/`: source registry, taxonomy, ACL, publish targets

Change rule:

- Update `platform/assembly/env-matrix.yaml` when profile-specific service map,
  smoke target, Argo sync, public HTTPS, or approval behavior changes.
- Update `release/platform-version.yaml` when a platform service reference or a
  routing/capability/knowledge/workflow/environment version reference changes.

Deployment truth is still executed from `apps/`, `cluster/`, `argocd-apps/`,
and `release/`.
