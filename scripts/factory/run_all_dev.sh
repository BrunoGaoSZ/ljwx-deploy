#!/usr/bin/env bash
set -euo pipefail

MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
CHECK_CMD="${CHECK_CMD:-bash scripts/ci/run_checks.sh}"
ISSUE_REPO="${ISSUE_REPO:-${GITHUB_REPOSITORY:-BrunoGaoSZ/ljwx-deploy}}"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "main" ]]; then
  echo "Run from a feature branch, not main."
  exit 1
fi

git push -u origin "$BRANCH"
PR_URL="$(gh pr view --json url -q .url 2>/dev/null || true)"
if [[ -z "$PR_URL" ]]; then
  PR_URL="$(gh pr create --fill --base main --head "$BRANCH" --json url -q .url)"
fi

echo "PR: $PR_URL"

ATTEMPT=1
while [[ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]]; do
  echo "Attempt $ATTEMPT/$MAX_ATTEMPTS: waiting checks"
  if gh pr checks "$PR_URL" --watch; then
    gh pr merge "$PR_URL" --squash --delete-branch
    echo "Merged: $PR_URL"
    exit 0
  fi

  bash scripts/repair/run.sh \
    --max-attempts 1 \
    --check-cmd "$CHECK_CMD" \
    --recipes repairs/recipes.yaml \
    --pr-url "$PR_URL" \
    --no-open-issue || true

  if git diff --quiet; then
    echo "No auto-fix changes produced"
    break
  fi

  git add -A
  git commit -m "chore(repair): auto-fix attempt ${ATTEMPT}"
  git push

  ATTEMPT=$((ATTEMPT + 1))
done

bash scripts/repair/run.sh \
  --max-attempts 1 \
  --check-cmd "bash -lc 'exit 1'" \
  --recipes repairs/recipes.yaml \
  --pr-url "$PR_URL" \
  --issue-repo "$ISSUE_REPO" \
  --allow-main || true

exit 1
