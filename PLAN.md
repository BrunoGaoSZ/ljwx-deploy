# Bid-MVP Factory Control Planes Implementation Plan (ljwx-deploy)

## Phase 0 Inventory

### Existing
- GitOps repo with Argo CD apps under `argocd-apps/` and workload manifests under `apps/`.
- Service images currently mostly controlled in overlay `kustomization.yaml` `images` blocks.
- Existing utility script: `scripts/create-app-secret.sh`.
- No `.github/workflows/` currently.

### Missing (to add)
- Evidence control plane:
  - `evidence/README.md`
  - `evidence/schema/evidence-record.schema.json`
  - `evidence/records/*.json`
  - generated `evidence/index.json`
- Evidence scripts:
  - `scripts/evidence/collect.py`
  - `scripts/evidence/validate.py`
- Pages site source:
  - `site/index.html`
  - `site/app.js`
  - optional `site/styles.css`
- GitHub Actions workflows:
  - nightly evidence collect + gh-pages publish
  - auto-repair (phase 5)
- Release queue and promoter:
  - `release/queue.yaml`
  - `scripts/promoter/deploy_promoter.py`
  - `scripts/promoter/README.md`
  - k8s CronJob manifests for promoter
- Dev image pin files:
  - `envs/dev/<service>.yaml`
- Smoke checks:
  - `scripts/smoke/run_smoke.py`
  - k8s smoke runner CronJob or Job manifest
- Auto repair loop:
  - `scripts/repair/recipes.yaml`
  - `scripts/repair/run_repair.py`

### Existing promoter/test-runner/evidence/pages status
- Promoter: not present.
- Test-runner/smoke runner: not present.
- Evidence model/feed: not present.
- Pages/gh-pages publishing workflow: not present.

## Phase 2 Scope (Evidence + Pages)
- Add evidence schema/model and scripts.
- Add nightly workflow that validates records, builds `evidence/index.json`, and publishes dashboard to `gh-pages` branch root.
- Keep GitHub as source of truth; no external state required.

## Phase 3 Scope (Release Queue + Auto Promote)
- Add queue state machine (`pending/promoted/failed`) with retry metadata.
- Add promoter logic for per-service serialization and supersede semantics.
- Verify Harbor digest existence via v2 manifest API (HEAD/GET) to avoid replication timing assumptions.
- Pin dev image in `envs/dev/<svc>.yaml` as digest reference.
- Write evidence records for promotion attempts/results.

## Phase 4 Scope (Post-deploy Smoke)
- Add smoke runner to check Argo app health/sync (or endpoint readiness fallback).
- Write smoke results into evidence record chain.

## Phase 5 Scope (Auto Repair Loop)
- Add repair recipes + runner for format/lint/codegen style fixes.
- Add automation notes/scripts for commit→PR→checks→auto-fix→recheck→merge (dev).
- Add fail-after-N behavior to open issue with minimal repro/logs.
- Add final `TEST.md` end-to-end dry run instructions.

## Phase-by-Phase Verification Commands (deploy repo)
- Phase 0:
  - `test -f PLAN.md && sed -n '1,120p' PLAN.md`
- Phase 2:
  - `python3 scripts/evidence/validate.py`
  - `python3 scripts/evidence/collect.py --out evidence/index.json`
  - `python3 -m json.tool evidence/index.json >/dev/null`
- Phase 3:
  - `python3 scripts/promoter/deploy_promoter.py --help`
  - `python3 scripts/promoter/deploy_promoter.py --dry-run`
- Phase 4:
  - `python3 scripts/smoke/run_smoke.py --help`
- Phase 5:
  - `python3 scripts/repair/run_repair.py --help`

## Commit Plan (deploy repo)
- `phase0(deploy): inventory + PLAN.md`
- `phase2(deploy): evidence model/scripts/pages workflow/site`
- `phase3(deploy): release queue + promoter + cronjob + runbook`
- `phase4(deploy): smoke runner + cronjob + evidence integration docs`
- `phase5(deploy): auto-repair recipes/runner + workflow + TEST.md`
