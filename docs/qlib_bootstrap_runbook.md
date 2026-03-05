# Qlib Bootstrap Runbook

## 1. 目标

- 周更离线生成 Qlib provider 数据与模型产物。
- 产物发布到 MinIO：
  - `qlib_data/cn/<BUILD_DATE>/...`
  - `qlib_data/cn/LATEST`
  - `artifacts/models/qlib_lightgbm_alpha158/<MODEL_DATE>/...`
  - `artifacts/models/qlib_lightgbm_alpha158/LATEST`

## 2. 前置条件

- PostgreSQL 已有 `ljwx_stock.market.kline_daily`，且 `adjust='qfq'` 非空。
- `qlib-pvc` 已绑定。
- `qlib-minio-secret` 在 `ljwx-stock` 命名空间存在。

## 3. 创建 qlib-minio-secret（推荐从 infra/minio-secret 复制）

```bash
MINIO_USER="$(kubectl -n infra get secret minio-secret -o jsonpath='{.data.MINIO_ROOT_USER}' | base64 -d)"
MINIO_PASS="$(kubectl -n infra get secret minio-secret -o jsonpath='{.data.MINIO_ROOT_PASSWORD}' | base64 -d)"

kubectl -n ljwx-stock create secret generic qlib-minio-secret \
  --from-literal=MINIO_ENDPOINT='http://minio.infra.svc.cluster.local:9000' \
  --from-literal=MINIO_BUCKET='ljwx-qlib' \
  --from-literal=MINIO_ACCESS_KEY="${MINIO_USER}" \
  --from-literal=MINIO_SECRET_KEY="${MINIO_PASS}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 4. 手动触发 bootstrap

```bash
kubectl -n ljwx-stock apply -f apps/stock-etl/base/job-qlib-bootstrap.yaml
kubectl -n ljwx-stock logs -f job/qlib-bootstrap-manual
```

## 5. 周期任务

- `cronjob/qlib-bootstrap-weekly` 每周六 03:00（Asia/Shanghai）执行。
- `cronjob/qlib-predict-to-pg` 每个交易日 16:30，先从 MinIO 同步到 PVC，再写 `market.reco_daily`。

## 6. 验收

```sql
SELECT trade_date, strategy_name, count(*)
FROM market.reco_daily
WHERE strategy_name = 'qlib_lightgbm_v1'
GROUP BY 1,2
ORDER BY trade_date DESC
LIMIT 5;
```

```bash
kubectl -n ljwx-stock get cronjob
kubectl -n ljwx-stock get jobs --sort-by=.metadata.creationTimestamp
```
