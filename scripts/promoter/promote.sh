#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DEPLOY_REPO_TOKEN:-}" && -z "${LOCAL_REPO_DIR:-}" ]]; then
  export LOCAL_REPO_DIR="$(pwd)"
fi

args=("$@")
if [[ "${SKIP_REGISTRY_CHECK:-0}" == "1" || "${SKIP_REGISTRY_CHECK:-}" == "true" || "${SKIP_REGISTRY_CHECK:-}" == "TRUE" ]]; then
  args+=("--skip-registry-check")
fi

python3 scripts/promoter/promote.py "${args[@]}"
