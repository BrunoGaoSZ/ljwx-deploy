# Qlib Bootstrap Runbook (ljwx-stock)

## Scope

- Service: `ljwx-stock-qlib-bootstrap`
- Namespace: `ljwx-stock`
- Deploy source: `apps/stock-etl/overlays/ljwx-stock`

## Runtime Manifests

- Weekly CronJob: `apps/stock-etl/base/cronjob-qlib-bootstrap-weekly.yaml`
- Manual Job template: `apps/stock-etl/base/job-qlib-bootstrap.yaml`
- Predict CronJob (consumer): `apps/stock-etl/base/cronjob-qlib-predict-to-pg.yaml`
- MinIO secret: `apps/stock-etl/base/secret-qlib-minio.yaml`

## Preconditions

1. `market.kline_daily` exists and has `adjust='qfq'` rows.
2. Secret `qlib-minio-secret` is present with valid keys:
   - `MINIO_ENDPOINT`
   - `MINIO_BUCKET`
   - `MINIO_ACCESS_KEY`
   - `MINIO_SECRET_KEY`
3. PVC `qlib-pvc` is Bound.

## Trigger Manual Bootstrap

```bash
kubectl -n ljwx-stock create job --from=job/qlib-bootstrap-manual qlib-bootstrap-manual-$(date +%Y%m%d%H%M%S)
```

Check status:

```bash
kubectl -n ljwx-stock get jobs | grep qlib-bootstrap-manual
kubectl -n ljwx-stock logs job/<job-name>
```

## Success Criteria

1. Job exits `Completed`.
2. Logs include preflight/export/dump/train/publish success path.
3. MinIO has both latest pointers:
   - `qlib_data/cn/LATEST`
   - `artifacts/models/qlib_lightgbm_alpha158/LATEST`
4. Predict CronJob can run and write to `market.reco_daily`.

## Common Failures

- `market.kline_daily not found`
  - Cause: ETL schema/data not ready.
  - Action: complete ETL migration/ingest first.
- `no qfq data`
  - Cause: no qfq-adjusted rows.
  - Action: verify ETL ingest mode and source quality.
- MinIO auth or bucket errors
  - Cause: invalid secret values.
  - Action: rotate/update `qlib-minio-secret`.

## Rollback

If new model/data is bad, repoint MinIO `LATEST` to previous known good date, then rerun predict CronJob:

1. set `qlib_data/cn/LATEST` to previous build date
2. set `artifacts/models/qlib_lightgbm_alpha158/LATEST` to previous model date
3. trigger predict run and verify `reco_daily`
