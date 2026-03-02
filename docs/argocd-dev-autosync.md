# ArgoCD Dev Auto-sync (OrbStack K8s)

This repo uses ArgoCD GitOps against GitHub `main`.

## If ArgoCD is not installed

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

## Bootstrap applications from this repo

```bash
kubectl apply -f argocd-apps/00-cluster-bootstrap.yaml
kubectl apply -f argocd-apps/01-apps-bootstrap.yaml
```

`01-apps-bootstrap` auto-manages `*-dev.yaml` application specs in `argocd-apps/`.

## GitHub-only source of truth

All `repoURL` values are set to:

`https://github.com/BrunoGaoSZ/ljwx-deploy.git`

## How auto-deploy works with promoter

1. Promoter writes `envs/dev/<svc>.yaml` digest pin and evidence.
2. ArgoCD tracks app manifests in `apps/*/overlays/*`.
3. Keep app overlay image refs aligned with promoted digest path (`harbor.omniverseai.net/app/<svc>@sha256:...`).
4. Argo auto-sync applies the new revision.

If auto-sync is disabled, fallback:

```bash
argocd app sync <app-name>
```
