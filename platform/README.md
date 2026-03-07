# Platform Config

This directory stores platform-level assembly artifacts that are not application source code:

- `assembly/`: environment matrix and capability registry
- `contracts/`: request, decision, and knowledge contracts
- `routing/`: route policies and model catalog
- `knowledge/`: source registry, taxonomy, ACL, publish targets

Deployment truth is still executed from `apps/`, `cluster/`, `argocd-apps/`, and `release/`.
