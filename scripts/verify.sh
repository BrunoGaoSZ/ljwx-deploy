#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[verify] validate release queue shape"
python3 scripts/promoter/validate_queue.py

echo "[verify] validate and collect evidence feed"
python3 scripts/evidence/validate.py
python3 scripts/evidence/collect.py --out /tmp/evidence-index.json --summary /tmp/evidence-latest.md

echo "[verify] run promoter dry-run on local repo"
python3 scripts/promoter/promote.py --dry-run --local-repo-dir .

echo
echo "[verify] Harbor digest check command:"
cat <<'CMD'
curl -u "${HARBOR_USER}:${HARBOR_PASS}" -I \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "https://harbor.omniverseai.net/v2/app/<service>/manifests/<digest>"
CMD

echo "[verify] done"
