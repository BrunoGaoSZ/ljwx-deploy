# End-to-End Dry Run (Bid-MVP Factory)

This dry run validates docs gates, evidence feed, promoter, smoke runner, and repair loop without secrets.

## 1. Docs Repo Checks (`ljwx-docs`)

```bash
cd ../ljwx-docs
test -f PLAN.md
rg --files docs/factory docs/templates .github/PULL_REQUEST_TEMPLATE
rg -n "Bid-MVP Factory|/factory/|/templates/" docs/.vitepress/config.ts
```

Note: `npm run docs:build` currently fails on existing repo dead links unrelated to this implementation.

## 2. Deploy Repo Checks (`ljwx-deploy`)

```bash
cd ../ljwx-deploy
test -f PLAN.md
bash scripts/verify.sh
uvx --with pyyaml --with jsonschema python scripts/evidence/validate.py
uvx --with pyyaml --with jsonschema python scripts/evidence/collect.py --out evidence/index.json
python3 -m json.tool evidence/index.json >/dev/null
```

## 3. Promoter Dry Run

```bash
uvx --with pyyaml python scripts/promoter/validate_queue.py
bash scripts/promoter/promote.sh --dry-run
```

Expected: script reports normalization/promotion simulation without commit/push.

Profile note:

- local k3s: `SERVICE_MAP_PATH=release/services.local-k3s.yaml`
- OrbStack k3s: `SERVICE_MAP_PATH=release/services.orbstack-k3s-cn.yaml`

## 4. Smoke Runner Dry Run

```bash
uvx --with pyyaml --with jsonschema python scripts/smoke/run_smoke.py --help
uvx --with pyyaml --with jsonschema python scripts/smoke/run_smoke.py --dry-run --targets scripts/smoke/targets.local-k3s.json
uvx --with pyyaml --with jsonschema python scripts/smoke/run_smoke.py --dry-run --targets scripts/smoke/targets.orbstack-k3s-cn.json
```

Expected: skips targets when no promoted records exist yet.

## 5. Repair Loop Dry Run

```bash
python3 scripts/repair/run_repair.py --help
python3 scripts/repair/diagnose.py --help
python3 scripts/repair/run_repair.py \
  --recipes repairs/recipes.yaml \
  --check-cmd "bash scripts/ci/run_checks.sh" \
  --max-attempts 1 \
  --log-dir .factory/repair/dryrun \
  --dry-run
bash scripts/repair/run.sh \
  --allow-main \
  --max-attempts 1 \
  --check-cmd "bash scripts/ci/run_checks.sh" \
  --recipes repairs/recipes.yaml \
  --dry-run
```

Expected: check passes or repair actions/logs are produced in `.factory/repair/dryrun`.

## 6. Pages Publish Workflow (Manual)

- Trigger workflow: `evidence-pages` (`workflow_dispatch`).
- Confirm `gh-pages` branch is updated by bot commit.
- Open dashboard URL: `https://brunogaosz.github.io/ljwx-deploy/`.
- Verify `Smoke` and `Promotion` columns render from `evidence/index.json`.

## 7. Full Dev Autopilot (Optional)

```bash
bash scripts/factory/run_all_dev.sh
```

Requires authenticated `gh` CLI and permissions to create/merge PRs and issues.

## 8. Repeatable Queue -> Promoted -> Smoke -> Evidence Acceptance

Run this after a queue PR has been merged (for example, `queue(ljwx-platform): ...`):

```bash
set -euo pipefail

# 1) Trigger promoter and smoke once (same logic as CronJob, no direct manifest patching).
PROMOTE_JOB="deploy-promoter-verify-$(date +%H%M%S)"
SMOKE_JOB="smoke-runner-verify-$(date +%H%M%S)"
kubectl -n dev create job --from=cronjob/deploy-promoter "${PROMOTE_JOB}"
kubectl -n dev create job --from=cronjob/smoke-runner "${SMOKE_JOB}"

# 2) Wait and print logs.
kubectl -n dev wait --for=condition=complete "job/${PROMOTE_JOB}" --timeout=600s
kubectl -n dev wait --for=condition=complete "job/${SMOKE_JOB}" --timeout=600s
kubectl -n dev logs "job/${PROMOTE_JOB}" --tail=200
kubectl -n dev logs "job/${SMOKE_JOB}" --tail=200

# 3) Verify queue/evidence result from git source of truth.
gh api 'repos/BrunoGaoSZ/ljwx-deploy/contents/release/queue.yaml?ref=main' -q '.content' \
  | tr -d '\n' | base64 -d | sed -n '1,140p'
gh api 'repos/BrunoGaoSZ/ljwx-deploy/contents/evidence/index.json?ref=main' -q '.content' \
  | tr -d '\n' | base64 -d | jq '.summary,.items[0]'
```

Success criteria:

- Queue entry moved from `pending` to `promoted` (or `failed` with explicit `lastError`).
- Latest evidence item has `deploy.status` and `tests.smoke.status`.
- `evidence/index.json` summary counters are updated.
