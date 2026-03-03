# ljwx-platform prod runtime config

This overlay deploys the backend image and runtime environment for k3s production-like clusters.

## Required runtime secret

Create `ljwx-platform-db` in namespace `ljwx-platform` before sync:

```bash
# Recommended scripted way
bash scripts/ops/sync-ljwx-platform-runtime-secret.sh ljwx-platform ljwx-platform-db

# Or manual way
kubectl create secret generic ljwx-platform-db \
  -n ljwx-platform \
  --from-literal=DB_USERNAME="$(kubectl -n infra get secret postgres-admin -o jsonpath='{.data.POSTGRES_USER}' | base64 -d)" \
  --from-literal=DB_PASSWORD="$(kubectl -n infra get secret postgres-admin -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)" \
  --from-literal=REDIS_PASSWORD="$(kubectl -n infra get secret redis-secret -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)" \
  --from-literal=JWT_SECRET="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The committed file `ljwx-platform-db.secret.example.yaml` is an example only and must not contain real credentials.

## Runtime policy

- `SPRING_PROFILES_ACTIVE=prod`
- DB host is infra service: `postgres-lb.infra.svc.cluster.local:5432`
- Redis host is infra service: `redis-lb.infra.svc.cluster.local:6379`
- Strict HTTP probes:
  - `/actuator/health/liveness`
  - `/actuator/health/readiness`
