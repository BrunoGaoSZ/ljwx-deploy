#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DEPLOY_REPO_TOKEN:-}" && -z "${LOCAL_REPO_DIR:-}" ]]; then
  export LOCAL_REPO_DIR="$(pwd)"
fi

python3 scripts/promoter/promote.py "$@"
