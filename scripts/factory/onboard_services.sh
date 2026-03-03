#!/usr/bin/env bash
set -euo pipefail

CATALOG_PATH="${1:-factory/onboarding/services.catalog.yaml}"
MODE="${2:-apply}"

if [[ "$MODE" == "dry-run" ]]; then
  uvx --with pyyaml python scripts/factory/onboard_services.py --catalog "$CATALOG_PATH" --dry-run
else
  uvx --with pyyaml python scripts/factory/onboard_services.py --catalog "$CATALOG_PATH"
fi
