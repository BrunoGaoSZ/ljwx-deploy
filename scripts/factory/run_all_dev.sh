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

  python3 scripts/repair/run_repair.py \
    --recipes scripts/repair/recipes.yaml \
    --check-cmd "$CHECK_CMD" \
    --max-attempts 1 \
    --log-dir ".factory/repair/${BRANCH}/attempt-${ATTEMPT}" || true

  if git diff --quiet; then
    echo "No auto-fix changes produced"
    break
  fi

  git add -A
  git commit -m "chore(repair): auto-fix attempt ${ATTEMPT}"
  git push

  ATTEMPT=$((ATTEMPT + 1))
done

python3 scripts/repair/run_repair.py \
  --recipes scripts/repair/recipes.yaml \
  --check-cmd "bash -lc 'exit 1'" \
  --max-attempts 1 \
  --log-dir ".factory/repair/${BRANCH}/final" \
  --issue-repo "$ISSUE_REPO" \
  --issue-title "Auto-repair exhausted for ${BRANCH}" \
  --open-issue-on-failure

exit 1
