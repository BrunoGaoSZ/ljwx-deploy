#!/usr/bin/env bash
set -euo pipefail

python3 scripts/evidence/validate.py
python3 scripts/evidence/collect.py --out evidence/index.json
python3 scripts/promoter/deploy_promoter.py --dry-run --skip-registry-check
python3 scripts/smoke/run_smoke.py --dry-run
