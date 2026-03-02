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
python3 scripts/evidence/validate.py
python3 scripts/evidence/collect.py --out evidence/index.json
python3 -m json.tool evidence/index.json >/dev/null
```

## 3. Promoter Dry Run

```bash
python3 scripts/promoter/validate_queue.py
bash scripts/promoter/promote.sh --dry-run
```

Expected: script reports normalization/promotion simulation without commit/push.

## 4. Smoke Runner Dry Run

```bash
python3 scripts/smoke/run_smoke.py --help
python3 scripts/smoke/run_smoke.py --dry-run
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
