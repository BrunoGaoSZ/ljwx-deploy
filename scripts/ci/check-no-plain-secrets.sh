#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CHANGED_FILE_LIST="${1:-$ROOT_DIR/.changed-files.txt}"

if [[ ! -f "$CHANGED_FILE_LIST" ]]; then
  echo "错误: 变更文件列表不存在: $CHANGED_FILE_LIST" >&2
  exit 2
fi

# High-signal secret patterns to block accidental plaintext commits.
PATTERNS=(
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----'
  '(ghp|github_pat)_[A-Za-z0-9_]+'
  '(?i)(password|passwd|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*"[^$<][^"]{8,}"'
  "(?i)(password|passwd|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*'[^$<][^']{8,}'"
)

allow_pattern='(example|dummy|sample|placeholder|<replace-me>|\$\{|\{\{)'
violations=0

while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  abs="$ROOT_DIR/$rel"
  [[ -f "$abs" ]] || continue

  for p in "${PATTERNS[@]}"; do
    if rg -n --pcre2 "$p" "$abs" >/tmp/secret-scan-match.txt 2>/dev/null; then
      if rg -n --pcre2 "$allow_pattern" /tmp/secret-scan-match.txt >/dev/null 2>&1; then
        continue
      fi
      echo "疑似明文凭证: $rel"
      cat /tmp/secret-scan-match.txt
      violations=1
      break
    fi
  done
done < "$CHANGED_FILE_LIST"

if [[ "$violations" -ne 0 ]]; then
  echo "错误: 检测到疑似明文凭证，请改为 Secret 注入。" >&2
  exit 1
fi

echo "No plaintext secret patterns detected."
