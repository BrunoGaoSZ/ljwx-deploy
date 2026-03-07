#!/usr/bin/env bash

set -euo pipefail

# This script exports runtime-contract directories for migration review.

OUT_DIR=""

usage() {
  cat <<'EOF'
用法:
  bash scripts/migrate/export-runtime-contract.sh --out <output-dir>
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$OUT_DIR" ]]; then
  echo "必须提供导出目录。" >&2
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEST_DIR="$(cd "$REPO_ROOT" && mkdir -p "$OUT_DIR" && cd "$OUT_DIR" && pwd)"
MANIFEST_FILE="$DEST_DIR/exported-runtime-contracts.txt"

echo "开始导出 runtime-contract 目录到: $DEST_DIR"
: > "$MANIFEST_FILE"

while IFS= read -r contract_dir; do
  rel_path="${contract_dir#"$REPO_ROOT"/}"
  target_dir="$DEST_DIR/$rel_path"
  mkdir -p "$(dirname "$target_dir")"
  cp -R "$contract_dir" "$target_dir"
  echo "$rel_path" >> "$MANIFEST_FILE"
done < <(find "$REPO_ROOT/apps" -type d -name runtime-contract | sort)

echo "导出完成，清单文件: $MANIFEST_FILE"
