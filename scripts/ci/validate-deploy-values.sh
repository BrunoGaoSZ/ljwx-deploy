#!/usr/bin/env bash
set -euo pipefail

FILE=""
BEFORE_FILE=""
FIXED_OTEL_ENDPOINT=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --file)
      FILE="${2:-}"
      shift 2
      ;;
    --before)
      BEFORE_FILE="${2:-}"
      shift 2
      ;;
    --fixed-otel-endpoint)
      FIXED_OTEL_ENDPOINT="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [ -z "$FILE" ]; then
  echo "--file is required"
  exit 1
fi

if [ ! -f "$FILE" ]; then
  echo "Target values file not found: $FILE"
  exit 1
fi

python3 - "$FILE" "$BEFORE_FILE" "$FIXED_OTEL_ENDPOINT" <<'PY'
import re
import sys
from pathlib import Path

import yaml

file_path = Path(sys.argv[1])
before_path = Path(sys.argv[2]) if sys.argv[2] else None
fixed_otel_endpoint = sys.argv[3]

data = yaml.safe_load(file_path.read_text()) or {}
required = ("deploymentId", "serviceVersion", "imageDigest")

missing = [k for k in required if not str(data.get(k, "")).strip()]
if missing:
    print(f"Hard rule failed: missing required fields: {', '.join(missing)}")
    sys.exit(1)

digest = str(data.get("imageDigest", "")).strip()
if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
    print("Hard rule failed: imageDigest must match sha256:<64 hex>")
    sys.exit(1)

if fixed_otel_endpoint:
    current_otel = str(data.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")).strip()
    if current_otel and current_otel != fixed_otel_endpoint:
        print("Hard rule failed: OTEL_EXPORTER_OTLP_ENDPOINT must remain fixed")
        sys.exit(1)

if before_path and before_path.exists() and before_path.stat().st_size > 0:
    old = yaml.safe_load(before_path.read_text()) or {}
    old_otel = str(old.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")).strip()
    new_otel = str(data.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")).strip()
    if old_otel != new_otel:
        print("Hard rule failed: OTEL_EXPORTER_OTLP_ENDPOINT changed")
        sys.exit(1)

print("Deploy values hard rules passed")
PY
