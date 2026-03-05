#!/usr/bin/env bash
set -euo pipefail

uvx --with pyyaml --with jsonschema python scripts/evidence/validate.py
uvx --with pyyaml --with jsonschema python scripts/evidence/collect.py --out evidence/index.json
uvx --with pyyaml python scripts/promoter/validate_queue.py
uvx --with pyyaml python scripts/promoter/queue_metrics.py --queue release/queue.yaml --out /tmp/queue-health.json
bash scripts/promoter/promote.sh --dry-run
uvx --with pyyaml --with jsonschema python scripts/smoke/run_smoke.py --dry-run --allow-failures
