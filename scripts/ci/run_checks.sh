#!/usr/bin/env bash
set -euo pipefail

python3 scripts/evidence/validate.py
python3 scripts/evidence/collect.py --out evidence/index.json
python3 scripts/promoter/validate_queue.py
bash scripts/promoter/promote.sh --dry-run
python3 scripts/smoke/run_smoke.py --dry-run
