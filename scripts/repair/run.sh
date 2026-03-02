#!/usr/bin/env bash
set -euo pipefail

MAX_ATTEMPTS=3
CHECK_CMD="bash scripts/ci/run_checks.sh"
RECIPES_FILE="repairs/recipes.yaml"
PR_URL=""
ISSUE_REPO="${GITHUB_REPOSITORY:-}"
OPEN_ISSUE=1
DRY_RUN=0
ALLOW_MAIN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      cat <<'USAGE'
Usage: bash scripts/repair/run.sh [options]

Options:
  --max-attempts N        Retry count (default: 3)
  --check-cmd CMD         Self-check command (default: bash scripts/ci/run_checks.sh)
  --recipes PATH          Repair recipes file (default: repairs/recipes.yaml)
  --pr-url URL            GitHub PR URL for check polling
  --issue-repo OWNER/REPO Target repo for failure issue (default: $GITHUB_REPOSITORY)
  --no-open-issue         Disable issue creation on exhaustion
  --dry-run               Do not push or open issues
  --allow-main            Allow execution on main branch
USAGE
      exit 0
      ;;
    --max-attempts)
      MAX_ATTEMPTS="$2"
      shift 2
      ;;
    --check-cmd)
      CHECK_CMD="$2"
      shift 2
      ;;
    --recipes)
      RECIPES_FILE="$2"
      shift 2
      ;;
    --pr-url)
      PR_URL="$2"
      shift 2
      ;;
    --issue-repo)
      ISSUE_REPO="$2"
      shift 2
      ;;
    --no-open-issue)
      OPEN_ISSUE=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --allow-main)
      ALLOW_MAIN=1
      shift
      ;;
    *)
      echo "unknown arg: $1"
      exit 2
      ;;
  esac
done

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$ALLOW_MAIN" != "1" && "$BRANCH" == "main" ]]; then
  echo "run.sh requires feature branch by default; pass --allow-main to override"
  exit 1
fi

if [[ -z "$PR_URL" ]] && command -v gh >/dev/null 2>&1; then
  PR_URL="$(gh pr view --json url -q .url 2>/dev/null || true)"
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_ROOT=".factory/repair/${BRANCH}/${RUN_ID}"
mkdir -p "$LOG_ROOT"

attempt=1
while [[ "$attempt" -le "$MAX_ATTEMPTS" ]]; do
  ATTEMPT_DIR="${LOG_ROOT}/attempt-${attempt}"
  mkdir -p "$ATTEMPT_DIR"
  CHECK_LOG="${ATTEMPT_DIR}/check.log"

  echo "[repair] attempt ${attempt}/${MAX_ATTEMPTS} running checks"
  set +e
  bash -lc "$CHECK_CMD" >"$CHECK_LOG" 2>&1
  CHECK_EXIT=$?
  set -e

  if [[ "$CHECK_EXIT" -eq 0 ]]; then
    echo "[repair] checks passed on attempt ${attempt}"
    exit 0
  fi

  DIAG_JSON="${ATTEMPT_DIR}/diagnose.json"
  python3 scripts/repair/diagnose.py \
    --check-log "$CHECK_LOG" \
    --recipes "$RECIPES_FILE" \
    --pr-url "$PR_URL" \
    --out "$DIAG_JSON"

  # Apply deterministic recipes selected from failed log context.
  python3 scripts/repair/run_repair.py \
    --recipes "$RECIPES_FILE" \
    --check-cmd "cat '$CHECK_LOG' && false" \
    --max-attempts 1 \
    --log-dir "${ATTEMPT_DIR}/repair" || true

  if git diff --quiet; then
    echo "[repair] no deterministic change generated"
    attempt=$((attempt + 1))
    continue
  fi

  git add -A
  if git diff --cached --quiet; then
    echo "[repair] nothing staged after fix"
    attempt=$((attempt + 1))
    continue
  fi

  if [[ -z "$(git config --get user.name || true)" ]]; then
    git config user.name "github-actions[bot]"
  fi
  if [[ -z "$(git config --get user.email || true)" ]]; then
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  fi

  git commit -m "chore(repair): deterministic auto-fix attempt ${attempt}"

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[repair] dry-run enabled, skip push"
  else
    git push
    if [[ -n "$PR_URL" ]] && command -v gh >/dev/null 2>&1; then
      gh pr checks "$PR_URL" --watch || true
    fi
  fi

  attempt=$((attempt + 1))
done

SUMMARY="${LOG_ROOT}/failure-summary.md"
cat >"$SUMMARY" <<EOT
# Auto-repair exhausted

- Branch: ${BRANCH}
- PR: ${PR_URL:-N/A}
- Max attempts: ${MAX_ATTEMPTS}
- Check command: ${CHECK_CMD}
- Log root: ${LOG_ROOT}

## Minimal Repro

\`\`\`bash
${CHECK_CMD}
\`\`\`

## Logs

- Diagnose and check logs are under: ${LOG_ROOT}
EOT

echo "[repair] exhausted after ${MAX_ATTEMPTS} attempts: ${SUMMARY}"

if [[ "$OPEN_ISSUE" == "1" && -n "$ISSUE_REPO" && "$DRY_RUN" != "1" ]] && command -v gh >/dev/null 2>&1; then
  TITLE="Auto-repair exhausted on ${BRANCH}"
  gh issue create -R "$ISSUE_REPO" --title "$TITLE" --body-file "$SUMMARY" >/dev/null || true
  echo "[repair] issue requested in ${ISSUE_REPO}"
fi

exit 1
