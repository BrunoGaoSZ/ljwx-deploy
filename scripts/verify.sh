#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[verify] validate release queue shape"
uvx --with pyyaml python scripts/promoter/validate_queue.py

echo "[verify] smart-cs contract gate"
bash scripts/ci/check-smart-cs-contract.sh

echo "[verify] smart-cs smoke targets gate"
bash scripts/ci/check-smart-cs-smoke-targets.sh

echo "[verify] ingress tls contract gate"
uvx --with pyyaml python scripts/ci/check-ingress-tls-contract.py

echo "[verify] validate onboarding catalog and platform profiles"
ONBOARD_FAIL_ON_DRIFT=true \
  bash scripts/factory/onboard_services.sh factory/onboarding/services.catalog.yaml dry-run

echo "[verify] validate and collect evidence feed"
uvx --with pyyaml --with jsonschema python scripts/evidence/validate.py
uvx --with pyyaml --with jsonschema python scripts/evidence/collect.py --out /tmp/evidence-index.json --summary /tmp/evidence-latest.md
uvx --with pyyaml python scripts/promoter/queue_metrics.py --queue release/queue.yaml --out /tmp/queue-health.json

echo "[verify] run promoter dry-run on local repo"
python3 scripts/promoter/promote.py --dry-run --local-repo-dir .
echo "[verify] promoter supports local simulation without Harbor via --skip-registry-check"

echo
echo "[verify] Harbor digest check command:"
cat <<'CMD'
curl -u "${HARBOR_USER}:${HARBOR_PASS}" -I \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "${HARBOR_URL}/v2/ljwx/<service>/manifests/<digest>"
CMD

echo "[verify] done"
